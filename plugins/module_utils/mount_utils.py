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
"""

from __future__ import annotations

from typing import Any, Optional, Union

from ansible_collections.o0_o.core.plugins.module_utils import (
    process_all_command_results,
    process_command_spec,
)

from ansible_collections.o0_o.posix.plugins.module_utils.filter_utils import (
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
                    f"Expected string option, got "
                    f"{type(opt).__name__}: {opt}"
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
        config = config.get("stdout") or ""

    parsed, errors = _parse_mount(str(config), "")
    if parsed is not None:
        return parsed
    if errors:
        raise errors[0]
    raise ValueError("Failed to parse mount output")


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
    """Process mount command results into structured facts.

    :param list[dict[str, Any]] cmds_completed: List of command
        result dicts from run plugin
    :returns tuple[dict[str, Any], list[Exception]]: Tuple of
        (facts_dict, errors) where facts_dict has o0_storage
        namespace key
    """
    processed = process_all_command_results(cmds_completed)
    errors = []

    mount_result = processed.get("mount")
    if mount_result is None:
        return {}, [ValueError("No mount result found")]

    errors.extend(mount_result.get("errors", []))
    mount_facts = mount_result.get("parsed")

    if mount_facts is None:
        return {}, errors

    return {"o0_storage": {"mounts": mount_facts}}, errors
