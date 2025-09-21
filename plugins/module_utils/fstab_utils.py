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

"""Fstab parsing and generation utilities."""

from __future__ import annotations

from typing import Any, Dict, List, Union

from ansible_collections.o0_o.posix.plugins.module_utils.jc_utils import (
    jc_parse,
)

from ansible_collections.o0_o.utils.plugins.module_utils import (
    string2items,
    wantlist,
)


def parse_fstab_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a single fstab entry from jc output to normalized format.

    Converts jc's fstab field names to standardized format:
    - fs_spec → source
    - fs_file → mount
    - fs_vfstype → type
    - fs_mntops → options (as list of dicts)
    - fs_freq → dump
    - fs_passno → pass

    :param entry: Single fstab entry from jc parser
    :returns: Normalized entry dict
    :raises ValueError: If required fields are missing
    """

    if not entry:
        raise ValueError("Empty fstab entry")

    norm_entry = {}

    # Required fields
    if "fs_spec" not in entry:
        raise ValueError("Missing fs_spec in fstab entry")
    if "fs_file" not in entry:
        raise ValueError("Missing fs_file in fstab entry")

    norm_entry["source"] = entry["fs_spec"]

    # Convert "none" to None for mount point
    mount = entry["fs_file"]
    norm_entry["mount"] = None if mount == "none" else mount

    # Parse filesystem type
    if "fs_vfstype" in entry:
        types = string2items(entry["fs_vfstype"])
        norm_entry["type"] = wantlist(types, False)
    else:
        norm_entry["type"] = None

    # Parse mount options into list of dicts
    norm_entry["options"] = []
    if "fs_mntops" in entry:
        options = string2items(entry["fs_mntops"])
        for opt in options:
            if "=" in opt:
                # Split on first = only
                key, value = opt.split("=", 1)
                norm_entry["options"].append({key: value})
            else:
                # Treat as boolean flag
                norm_entry["options"].append({opt: True})

    # Parse dump frequency
    if "fs_freq" in entry:
        try:
            norm_entry["dump"] = int(entry["fs_freq"])
        except (TypeError, ValueError):
            # Non-integer values become None
            norm_entry["dump"] = None
    else:
        norm_entry["dump"] = None

    # Parse fsck pass number
    if "fs_passno" in entry:
        try:
            norm_entry["pass"] = int(entry["fs_passno"])
        except (TypeError, ValueError):
            # Non-integer values become None
            norm_entry["pass"] = None
    else:
        norm_entry["pass"] = None

    return norm_entry


def generate_fstab_entry(entry: Dict[str, Any]) -> str:
    """Generate an fstab line from a normalized entry dict.

    Converts normalized format back to fstab line:
    - source → fs_spec
    - mount → fs_file (None becomes "none")
    - type → fs_vfstype
    - options → fs_mntops (defaults to "defaults" if not provided)
    - dump → fs_freq (defaults to 0)
    - pass → fs_passno (defaults based on mount point and fs type)

    Default pass values:
    - 1 for root filesystem (/)
    - 2 for other regular filesystems
    - 0 for swap, tmpfs, proc, sysfs, network filesystems

    :param entry: Normalized entry dict
    :returns: Formatted fstab line
    :raises ValueError: If required fields are missing
    """
    if not entry:
        raise ValueError("Empty fstab entry")

    # Required fields
    if "source" not in entry:
        raise ValueError("Missing source in fstab entry")
    if "mount" not in entry:
        raise ValueError("Missing mount in fstab entry")

    # Build the line components
    source = entry["source"]
    # Convert None to "none" for mount point (common for swap)
    mount = "none" if entry["mount"] is None else entry["mount"]

    # Type defaults to "auto" if not specified
    fs_type = entry.get("type", "auto")
    if isinstance(fs_type, list):
        # If multiple types, use the first one
        fs_type = fs_type[0] if fs_type else "auto"

    # Build options string - default to "defaults" if none provided
    if "options" in entry and entry["options"]:
        options_parts = []
        for opt_dict in entry["options"]:
            for key, value in opt_dict.items():
                if value is True:
                    # Boolean flag
                    options_parts.append(key)
                else:
                    # Key=value pair
                    options_parts.append(f"{key}={value}")
        options_str = ",".join(options_parts) if options_parts else "defaults"
    else:
        # No options provided, use defaults
        options_str = "defaults"

    # Dump defaults to 0 (most modern systems don't use dump)
    if "dump" in entry:
        dump = entry["dump"]
        if dump is None:
            dump = 0
    else:
        dump = 0

    # Pass - defaults based on mount point and filesystem type
    if "pass" in entry:
        fsck_pass = entry["pass"]
        if fsck_pass is None:
            fsck_pass = 0
    else:
        # Determine sensible default for pass
        # Filesystem types that should not be checked
        no_fsck_types = {
            "swap",
            "tmpfs",
            "proc",
            "sysfs",
            "devpts",
            "devtmpfs",
            "cgroup",
            "cgroup2",
            "debugfs",
            "securityfs",
            "pstore",
            "configfs",
            "fusectl",
            "mqueue",
            "hugetlbfs",
            "rpc_pipefs",
            "nfs",
            "nfs4",
            "cifs",
            "smb",
            "smbfs",
            "autofs",
            "fuse",
            "binfmt_misc",
            "ramfs",
            "vfat",
            "ntfs",
            "iso9660",
            "udf",
        }

        # Check if this is a virtual/network/special filesystem
        if fs_type.lower() in no_fsck_types:
            fsck_pass = 0
        elif fs_type.startswith("fuse."):
            fsck_pass = 0
        elif mount == "none" or entry["mount"] is None:
            # Swap or other special mount
            fsck_pass = 0
        elif mount == "/":
            # Root filesystem should be checked first
            fsck_pass = 1
        else:
            # Other regular filesystems checked second
            fsck_pass = 2

    # Format with proper spacing (common fstab convention)
    # Use tabs for alignment, which is typical in fstab files
    return f"{source}\t{mount}\t{fs_type}\t{options_str}\t{dump}\t{fsck_pass}"


def parse_fstab(content: str) -> List[Dict[str, Any]]:
    """Parse fstab content into normalized list of entries.

    :param content: Fstab content as string
    :returns: List of normalized entry dicts
    :raises ValueError: If parsing fails
    :raises ImportError: If jc is not available
    """
    # Parse with jc_parse
    try:
        parsed = jc_parse("fstab", content)
    except Exception as e:
        raise ValueError(f"Failed to parse fstab content: {e}") from e

    # Normalize each entry
    normalized = []
    for entry in parsed:
        try:
            norm_entry = parse_fstab_entry(entry)
            normalized.append(norm_entry)
        except ValueError:
            # Skip invalid entries (we can't use display to warn)
            continue

    return normalized


def generate_fstab(entries: List[Dict[str, Any]]) -> str:
    """Generate fstab content from normalized list of entries.

    :param entries: List of normalized entry dicts
    :returns: Formatted fstab content
    :raises ValueError: If generation fails
    """
    if not entries:
        return ""

    lines = []

    # Generate each entry
    for entry in entries:
        try:
            line = generate_fstab_entry(entry)
            lines.append(line)
        except ValueError:
            # Skip invalid entries
            continue

    return "\n".join(lines) + "\n"


def fstab(
    config: Union[str, Dict[str, Any], List[Dict[str, Any]]],
) -> Union[List[Dict[str, Any]], str]:
    """Process fstab data - parse or generate based on input type.

    Bidirectional processor that either:
    1. Parses fstab text into normalized list of mount entries
    2. Generates fstab text from list of mount entries

    For parsing (string input):
    - fs_spec → source
    - fs_file → mount
    - fs_vfstype → type
    - fs_mntops → options (as list of dicts)
    - fs_freq → dump
    - fs_passno → pass

    For generation (list of dicts input):
    - source → fs_spec
    - mount → fs_file
    - type → fs_vfstype
    - options → fs_mntops (comma-separated)
    - dump → fs_freq
    - pass → fs_passno

    :param config: Fstab text to parse or list of entries to generate
    :returns: Either parsed entries list or generated fstab text
    :raises ValueError: If parsing or generation fails
    :raises ImportError: If jc is not available
    """
    # Check if this is a list input (for generation)
    if isinstance(config, list):
        # List of dicts - check if it's for generation
        if config and isinstance(config[0], dict):
            if "source" in config[0] and "mount" in config[0]:
                # Generate fstab from entries
                return generate_fstab(config)
            else:
                # List of dicts but not normalized entries
                raise ValueError(
                    "List of dicts must have 'source' and 'mount' keys "
                    "for generation"
                )
        else:
            raise ValueError(
                "List input is only supported for generation with dict entries"
            )

    # Handle dict input (e.g., from command module)
    if isinstance(config, dict):
        # Single entry dict for generation
        if "source" in config and "mount" in config:
            return generate_fstab([config])
        # Otherwise try to parse as command result
        # jc_parse will handle stdout/content extraction

    # Parse with jc_parse (handles both string and dict inputs)
    parsed = jc_parse("fstab", config)

    # Normalize each entry
    normalized = []
    for entry in parsed:
        try:
            norm_entry = parse_fstab_entry(entry)
            normalized.append(norm_entry)
        except ValueError:
            # Skip invalid entries
            continue

    return normalized
