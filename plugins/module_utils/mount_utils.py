# vim: ts=4:sw=4:sts=4:et:ft=python
# -*- mode: python; tab-width: 4; indent-tabs-mode: nil; -*-
#
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later
# (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
#
# Copyright (c) 2025 oØ.o (@o0-o)
#
# This file is part of the o0_o.posix Ansible Collection.

"""Mount parsing utilities.

The canonical parser is ``_parse_mount`` which implements the
COMMAND_SPEC ``(output, e_prefix) -> (parsed, errors)`` contract.

``compose_mounts`` is the one definition of the mounts fact: what
``df`` reports, keyed by mount point and carrying the capacity only
``df`` knows, with the type and options only ``mount`` knows merged
in.  Every producer of the fact composes it here so consumers see one
shape.

``compose_mount_config`` is the second half of that composition, and
it cannot ride the same batch: what a filesystem says about itself is
asked at its mountpoint, and the mountpoints are what the first batch
answered with.  Every producer joins it here for the same reason it
composes the rest here.
"""

from __future__ import annotations

from typing import Any, Optional, Union

from ansible_collections.o0_o.core.plugins.module_utils import (
    process_all_command_results,
    process_command_spec,
)

from ansible_collections.o0_o.posix.plugins.module_utils.filter_utils import (
    decode_declared_content,
    normalize_source,
)
from ansible_collections.o0_o.posix.plugins.module_utils.jc_utils import (
    jc_parse,
)

# Mount option normalization mappings
# These options have no/no* prefixes that should be normalized to
# booleans
BOOLEAN_OPTION_PAIRS = {
    # Standard POSIX options
    "exec": "noexec",
    "suid": "nosuid",
    "dev": "nodev",
    "diratime": "nodiratime",
    "user": "nouser",
    "mand": "nomand",
    # Extended attributes and ACLs
    "acl": "noacl",
    "user_xattr": "nouser_xattr",
    # Filesystem features
    "quota": "noquota",
    "iversion": "noiversion",
    # NFS-specific options
    "intr": "nointr",
    "cto": "nocto",
    "lock": "nolock",
    "rdirplus": "nordirplus",
    # Ext* filesystem options
    "journal_async_commit": "nojournal_async_commit",
}

# Special mappings that don't follow the no* pattern
SPECIAL_MAPPINGS = {
    "rw": ("writable", True),
    "ro": ("writable", False),
    "sync": ("sync", True),
    "async": ("sync", False),
    "hard": ("hard", True),  # NFS
    "soft": ("hard", False),  # NFS
}

# Atime options get special handling as an enum
# Values: True (normal atime), False (noatime), "relative", "strict"
ATIME_OPTIONS = {
    "atime": True,  # Normal access time updates
    "noatime": False,  # No access time updates
    "relatime": "relative",  # Update atime relative to mtime/ctime
    "strictatime": "strict",  # Always update atime (kernel default)
}

# Filesystem type categories the mounts fact is selected by
VIRTUAL_FS_TYPES = {
    "tmpfs",
    "devtmpfs",
    "proc",
    "sysfs",
    "devpts",
    "securityfs",
    "cgroup",
    "cgroup2",
    "debugfs",
    "tracefs",
    "configfs",
    "fusectl",
    "pstore",
    "efivarfs",
    "bpf",
    "autofs",
    "mqueue",
    "hugetlbfs",
    "rpc_pipefs",
    "binfmt_misc",
    "ramfs",
}

NETWORK_FS_TYPES = {
    "nfs",
    "nfs4",
    "cifs",
    "smb",
    "smbfs",
    "ncpfs",
    "ncp",
    "afs",
    "coda",
    "ftpfs",
    "sshfs",
    "webdav",
    "davfs",
}

OVERLAY_FS_TYPES = {"overlay", "overlayfs", "aufs", "unionfs"}

# Pseudo filesystems, a subset of the virtual ones
PSEUDO_FS_TYPES = {
    "proc",
    "sysfs",
    "devpts",
    "devtmpfs",
    "securityfs",
    "debugfs",
    "tracefs",
    "configfs",
    "fusectl",
    "pstore",
    "efivarfs",
    "bpf",
    "cgroup",
    "cgroup2",
    "mqueue",
    "hugetlbfs",
    "rpc_pipefs",
}

# Which categories a producer reports when it is not told otherwise.
# A virtual filesystem stores nothing that outlives a boot, so it
# stays out of the answer both producers give.  ``pseudo`` follows
# ``virtual`` wherever it is left unset.
MOUNT_FILTER_DEFAULTS = {
    "device": True,
    "virtual": False,
    "network": True,
    "pseudo": None,
    "overlay": True,
    "fuse": True,
}


def normalize_mount_options(options: dict[str, Any]) -> dict[str, Any]:
    """Normalize mount options to use consistent boolean format.

    Converts options like noexec to exec=False, ro to writable=False,
    etc. Atime options are normalized to an enum: True, False,
    "relative", or "strict".
    Any option not in our mappings is treated as a boolean True flag.

    :param options: Raw options dict from parsing
    :returns: Normalized options dict with consistent boolean values
    """
    normalized = {}

    # Create reverse mapping for no* options
    reverse_boolean = {v: k for k, v in BOOLEAN_OPTION_PAIRS.items()}

    for opt, value in options.items():
        # Trim whitespace. Some platforms (e.g., OpenBSD) may print
        # tokens with a leading space, like " nosuid".
        opt = opt.strip()
        if not opt:
            continue
        # Check atime options first (they override each other)
        if opt in ATIME_OPTIONS:
            normalized["atime"] = ATIME_OPTIONS[opt]
        # Check special mappings (rw/ro, sync/async, etc.)
        elif opt in SPECIAL_MAPPINGS:
            key, bool_value = SPECIAL_MAPPINGS[opt]
            normalized[key] = bool_value
        # Check if it's a positive option (exec, dev, suid, etc.)
        elif opt in BOOLEAN_OPTION_PAIRS:
            normalized[opt] = True
        # Check if it's a negative option (noexec, nodev, nosuid, etc.)
        elif opt in reverse_boolean:
            normalized[reverse_boolean[opt]] = False
        # Options with values stay as-is
        elif value is not True:
            normalized[opt] = value
        # Any other option defaults to boolean True
        else:
            normalized[opt] = True

    # If no atime option was seen, don't set a default
    # (let the system use its default behavior)

    return normalized


def parse_mount_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Parse a single mount entry from jc output to normalized format.

    Converts jc's mount field names to standardized format:
    - filesystem → source
    - mount_point → mount
    - type → type (extracted from type field or first option)
    - options → options (as merged dict, unlike fstab's list of dicts)

    :param entry: Single mount entry from jc parser
    :returns: Normalized entry dict
    :raises ValueError: If required fields are missing
    :raises TypeError: If options are not strings
    """
    if not entry:
        raise ValueError("Empty mount entry")

    norm_entry = {}

    # Required fields
    if "filesystem" not in entry:
        raise ValueError("Missing filesystem in mount entry")
    if "mount_point" not in entry:
        raise ValueError("Missing mount_point in mount entry")

    norm_entry["source"] = normalize_source(entry["filesystem"])
    norm_entry["mount"] = entry["mount_point"]

    # Parse filesystem type
    if "type" in entry:
        # Linux style - explicit type field
        norm_entry["type"] = entry["type"]
    elif "options" in entry and entry["options"]:
        # macOS/FreeBSD style - type is first option
        options = list(entry["options"])
        norm_entry["type"] = options.pop(0)
        entry = dict(entry)  # Make a copy to avoid modifying original
        entry["options"] = options
    else:
        # No type information available
        norm_entry["type"] = None

    # Parse mount options into a merged dict (unlike fstab which uses
    # list of dicts)
    raw_options = {}
    if "options" in entry and entry["options"]:
        for opt in entry["options"]:
            if not isinstance(opt, str):
                raise TypeError(
                    f"Expected string option, got {type(opt).__name__}: {opt}"
                )
            # Skip empty strings
            if not opt:
                continue
            # Normalize whitespace around the token
            opt = opt.strip()
            if not opt:
                continue
            if "=" in opt:
                # Split on first = only
                key, value = opt.split("=", 1)
                raw_options[key.strip()] = value
            else:
                # Treat as boolean flag
                raw_options[opt] = True

    # Normalize the options to consistent boolean format
    norm_entry["options"] = normalize_mount_options(raw_options)

    return norm_entry


def parse_mount(content: str) -> list[dict[str, Any]]:
    """Parse mount output into normalized list of entries.

    :param content: Mount output as string
    :returns: List of normalized entry dicts matching fstab structure
    :raises ValueError: If parsing fails
    :raises ImportError: If jc is not available
    """
    # Parse with jc_parse
    try:
        parsed = jc_parse("mount", content)
    except Exception as e:
        raise ValueError(f"Failed to parse mount output: {e}") from e

    # Normalize each entry
    normalized = []
    for entry in parsed:
        try:
            norm_entry = parse_mount_entry(entry)
            normalized.append(norm_entry)
        except ValueError:
            # Skip invalid entries (we can't use display to warn)
            continue

    return normalized


def _parse_mount(
    output: str,
    e_prefix: str,
) -> tuple[Optional[list[dict[str, Any]]], Optional[list[Exception]]]:
    """Canonical COMMAND_SPEC parser for mount command output.

    Parses raw mount stdout into a list of normalized mount entry
    dicts.

    :param str output: Raw stdout from ``mount``
    :param str e_prefix: Error prefix for context
    :returns tuple[Optional[list[dict[str, Any]]], Optional[list[Exception]]]:
        Parsed mount entries and list of errors
    """
    errors = []
    text = (output or "").strip()
    if not text:
        errors.append(ValueError(f"{e_prefix}Empty mount output"))
        return None, errors

    try:
        parsed = jc_parse("mount", text)
    except Exception as e:
        errors.append(ValueError(f"{e_prefix}Failed to parse mount: {e}"))
        return None, errors

    normalized = []
    for entry in parsed:
        try:
            norm_entry = parse_mount_entry(entry)
            normalized.append(norm_entry)
        except ValueError:
            continue

    return normalized, errors


def mount(config: Union[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse mount command output into structured format.

    Convenience wrapper around ``_parse_mount`` for filter use.

    :param config: Mount command output as string or dict
    :returns: List of normalized mount entries
    :raises ValueError: If parsing fails
    :raises ImportError: If jc is not available
    """
    if isinstance(config, dict):
        if "stdout" in config:
            config = config.get("stdout") or ""
        elif "content" in config:
            content = config["content"]
            # A read or slurp result declares an encoded content
            declared = decode_declared_content(content, config.get("encoding"))
            config = content if declared is None else declared
        else:
            config = ""

    parsed, errors = _parse_mount(str(config), "")
    if parsed is not None:
        return parsed
    if errors:
        raise errors[0]
    raise ValueError("Failed to parse mount output")


def include_mount(
    entry: dict[str, Any],
    filters: Optional[dict[str, Any]] = None,
) -> bool:
    """Decide whether a mount belongs in the fact.

    :param dict[str, Any] entry: Composed mount entry
    :param Optional[dict[str, Any]] filters: Category selections,
        defaulting to MOUNT_FILTER_DEFAULTS for anything unnamed
    :returns bool: True when the entry should be reported
    """
    selected = dict(MOUNT_FILTER_DEFAULTS)
    selected.update(
        {k: v for k, v in (filters or {}).items() if v is not None}
    )
    if selected["pseudo"] is None:
        selected["pseudo"] = selected["virtual"]

    fs_type = entry.get("type") or ""

    is_virtual = fs_type in VIRTUAL_FS_TYPES
    is_network = fs_type in NETWORK_FS_TYPES
    is_overlay = fs_type in OVERLAY_FS_TYPES
    is_pseudo = fs_type in PSEUDO_FS_TYPES
    is_fuse = fs_type.startswith("fuse")

    # A device filesystem is one in no other category
    is_device = not (is_virtual or is_network or is_overlay or is_fuse)

    categories = (
        ("device", is_device),
        ("virtual", is_virtual),
        ("network", is_network),
        ("overlay", is_overlay),
        ("pseudo", is_pseudo),
        ("fuse", is_fuse),
    )

    return not any(
        member and not selected[name] for name, member in categories
    )


def compose_mounts(
    df_entries: list[dict[str, Any]],
    mount_entries: list[dict[str, Any]],
    filters: Optional[dict[str, Any]] = None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Compose the canonical mounts fact from df and mount.

    The fact is keyed by mount point, so the ``mount`` field each
    parser reports becomes the key rather than a field.  ``df`` names
    what is mounted and how much of it is used; ``mount`` names the
    filesystem type and the options it was mounted with.  A mount
    point ``df`` did not report is not reported here either: without
    ``df`` there is no capacity, and half the fact under the same name
    is the drift this composition exists to end.

    Where the two commands disagree about a mount point's source,
    ``df`` is taken and the disagreement is described in the returned
    notes, for a caller with somewhere to put them.

    :param list[dict[str, Any]] df_entries: Parsed ``df -P`` entries
    :param list[dict[str, Any]] mount_entries: Parsed ``mount`` entries
    :param Optional[dict[str, Any]] filters: Category selections, see
        ``include_mount``
    :returns tuple[dict[str, dict[str, Any]], list[str]]: The mounts
        fact keyed by mount point, and notes about source
        disagreements
    """
    mounts: dict[str, dict[str, Any]] = {}
    notes: list[str] = []

    for entry in df_entries:
        entry = dict(entry)
        mountpoint = entry.pop("mount", None)
        if mountpoint:
            mounts[mountpoint] = entry

    for entry in mount_entries:
        mountpoint = entry.get("mount")
        if not mountpoint or mountpoint not in mounts:
            continue

        composed = mounts[mountpoint]

        for field in ("type", "options"):
            if field in entry:
                composed[field] = entry[field]

        df_source = composed.get("source")
        mount_source = entry.get("source")
        if df_source and mount_source and df_source != mount_source:
            notes.append(
                f"Mount point {mountpoint}: df reports source as"
                f" '{df_source}' but mount reports '{mount_source}'."
                f" Using df source."
            )

    return {
        mountpoint: entry
        for mountpoint, entry in mounts.items()
        if include_mount(entry, filters)
    }, notes


def compose_mount_config(
    mounts: dict[str, dict[str, Any]],
    pathconf: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Join each mount to what its filesystem said about itself.

    The ``pathconf`` class is asked at a pathname, and a mountpoint is
    the pathname that names the filesystem mounted there, so what it
    answers is a fact about the mount and lands on the mount's entry.
    The join is the mountpoint, which both sides are already keyed by.

    A mount whose filesystem answered nothing carries no ``config`` at
    all rather than an empty one, the same way a variable the host
    does not know is absent from the host's own configuration: an
    empty mapping would claim a filesystem was asked and had nothing
    to say, which is a different answer from not having been asked.

    :param dict[str, dict[str, Any]] mounts: The composed mounts fact,
        keyed by mount point
    :param dict[str, dict[str, Any]] pathconf: What each path
        answered, keyed by path and then by variable
    :returns dict[str, dict[str, Any]]: The same mounts, each carrying
        its filesystem's configuration where there was one
    """
    for mountpoint, entry in mounts.items():
        config = pathconf.get(mountpoint)
        if config:
            entry["config"] = config

    return mounts


def get_mount_command_requests() -> list[dict[str, Any]]:
    """Build command requests for mount fact gathering.

    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (  # noqa: E501
        MOUNT_COMMAND_SPEC,
    )

    return process_command_spec(MOUNT_COMMAND_SPEC)


def process_mount_command_results(
    cmds_completed: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[Exception]]:
    """Process df and mount results into the mounts fact.

    Both commands feed one fact, composed the way the mounts module
    composes it, so a gather and a standalone run answer alike.

    :param list[dict[str, Any]] cmds_completed: List of command
        result dicts from run plugin
    :returns tuple[dict[str, Any], list[Exception]]: Tuple of
        (facts_dict, errors) where facts_dict has o0_storage
        namespace key
    """
    processed = process_all_command_results(cmds_completed)
    errors: list[Exception] = []

    df_result = processed.get("df")
    mount_result = processed.get("mount")
    if df_result is None or mount_result is None:
        missing = "df" if df_result is None else "mount"
        return {}, [ValueError(f"No {missing} result found")]

    errors.extend(df_result.get("errors", []))
    errors.extend(mount_result.get("errors", []))

    df_entries = df_result.get("parsed")
    mount_entries = mount_result.get("parsed")

    # Capacity comes from df alone, so a df that did not answer
    # leaves the fact unpublished rather than published short a half.
    if df_entries is None or mount_entries is None:
        return {}, errors

    mounts, _notes = compose_mounts(df_entries, mount_entries)

    return {"o0_storage": {"mounts": mounts}}, errors
