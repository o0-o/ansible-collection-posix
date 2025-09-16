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

"""Mount parsing utilities."""

from __future__ import annotations

from typing import Any, Dict, List, Union

from ansible_collections.o0_o.posix.plugins.module_utils.filter_utils import (
    process_registered_result,
)

try:
    import jc
    HAS_JC = True
except ImportError:
    HAS_JC = False


def parse_mount_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a single mount entry from jc output to normalized format.

    Converts jc's mount field names to standardized format:
    - filesystem → source
    - mount_point → mount
    - type → type (extracted from type field or first option)
    - options → options (as list of dicts)

    :param entry: Single mount entry from jc parser
    :returns: Normalized entry dict
    :raises ValueError: If required fields are missing
    """
    if not entry:
        raise ValueError("Empty mount entry")

    norm_entry = {}

    # Required fields
    if "filesystem" not in entry:
        raise ValueError("Missing filesystem in mount entry")
    if "mount_point" not in entry:
        raise ValueError("Missing mount_point in mount entry")

    norm_entry["source"] = entry["filesystem"]
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

    # Parse mount options into list of dicts (matching fstab structure)
    norm_entry["options"] = []
    if "options" in entry and entry["options"]:
        for opt in entry["options"]:
            if isinstance(opt, str):
                # Skip empty strings
                if not opt:
                    continue
                if "=" in opt:
                    # Split on first = only
                    key, value = opt.split("=", 1)
                    norm_entry["options"].append({key: value})
                else:
                    # Treat as boolean flag
                    norm_entry["options"].append({opt: True})
            else:
                # Already structured (shouldn't happen with jc)
                norm_entry["options"].append({str(opt): True})

    return norm_entry


def parse_mount(content: str) -> List[Dict[str, Any]]:
    """Parse mount output into normalized list of entries.

    :param content: Mount output as string
    :returns: List of normalized entry dicts matching fstab structure
    :raises ValueError: If parsing fails
    :raises ImportError: If jc is not available
    """
    if not HAS_JC:
        raise ImportError("jc library is required for mount parsing")

    # Parse with jc
    try:
        parsed = jc.parse("mount", content)
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


def mount(config: Union[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Process mount data - parse command output into structured format.

    Mount is unidirectional - only parses mount output.
    Returns data structure matching fstab format:
    - source: device or filesystem source
    - mount: mount point path
    - type: filesystem type (string, never a list)
    - options: list of dicts with mount options

    Note: Unlike fstab, mount doesn't have dump or pass fields.

    :param config: Mount command output as string or dict
    :returns: List of normalized mount entries
    :raises ValueError: If parsing fails
    :raises ImportError: If jc is not available
    """
    # Handle dict input (e.g., from command module or slurp)
    if isinstance(config, dict):
        if "stdout" in config or "content" in config:
            # Use shared utility for registered result processing
            return process_registered_result(config, parse_mount)
        else:
            raise ValueError(
                "Dict input must have 'stdout' or 'content' key for parsing"
            )

    # Parse mount output string
    return parse_mount(config)
