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

"""Filter processing utilities."""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, Optional, Union
import base64


def process_registered_result(
    config: Dict[str, Any], parser: Callable[[Union[str, list]], Any]
) -> Any:
    """Process registered result dict with automatic base64 detection.

    Handles dict input from registered results (command/slurp modules):
    - Extracts content from 'stdout' or 'content' keys
    - Automatically detects and decodes base64 for 'content' key
    - Falls back to base64 decode on parse errors

    :param config: Dict with registered result from command or slurp
    :param parser: Function to parse the extracted content
    :returns: Result from parser function
    :raises ValueError: If dict doesn't have required keys or fails
    """
    if "stdout" in config:
        content = config["stdout"]
        # stdout is never base64 encoded
        return parser(content)
    elif "content" in config:
        content = config["content"]
        # content from slurp is usually base64 encoded
        # Try parsing as-is first (in case it's not encoded)
        try:
            return parser(content)
        except (ValueError, Exception) as e:
            # Try base64 decode and parse
            try:
                decoded = base64.b64decode(content).decode("utf-8")
                return parser(decoded)
            except Exception:
                # Not base64 or decode failed, raise original error
                raise e
    else:
        raise ValueError(
            "Dict input must have 'stdout' or 'content' key for parsing"
        )


def normalize_source(source: str) -> Optional[Dict[str, Any]]:
    """Normalize a mount/df source into a structured dictionary.

    Parses various source formats into a consistent structure:
    - Device paths: /dev/sda1, /dev/disk3s1s1
    - Network paths: server:/export, //server/share
    - UUID: UUID=abc-123, PARTUUID=def-456
    - Labels: LABEL=root, PARTLABEL=system
    - Special filesystems: proc, sysfs, tmpfs, devpts
    - Automounter maps: map auto_home, map -hosts
    - Special cases: "none" or "-" return None

    :param source: The source string from mount or df output
    :returns: Dict with structured source information, or None

    Return dict contains applicable fields:
    - path: Local device path (e.g., /dev/sda1)
    - address: Network address (e.g., server:/export)
    - map: Automounter map name
    - name: Special filesystem name (e.g., proc, tmpfs)
    - uuid: UUID value
    - label: Label value
    - partition: Boolean indicating if UUID/LABEL is partition-specific
    """
    # Handle special cases that should return None
    if source in ("none", "-"):
        return None

    result: Dict[str, Any] = {}

    # Check for UUID formats
    uuid_match = re.match(r"^(PART)?(UUID)=(.+)$", source, re.IGNORECASE)
    if uuid_match:
        result["uuid"] = uuid_match.group(3)
        result["partition"] = bool(uuid_match.group(1))
        return result

    # Check for LABEL formats
    label_match = re.match(r"^(PART)?(LABEL)=(.+)$", source, re.IGNORECASE)
    if label_match:
        result["label"] = label_match.group(3)
        result["partition"] = bool(label_match.group(1))
        return result

    # Check for automounter maps
    if source.startswith("map "):
        result["map"] = source[4:]  # Remove 'map ' prefix
        return result

    # Check for network paths (NFS, SMB/CIFS)
    # NFS: server:/path or server.domain:/path
    # SMB: //server/share
    if ":" in source and "/" in source:
        # NFS style: host:/path
        if not source.startswith("//"):
            result["address"] = source
            return result
    elif source.startswith("//"):
        # SMB/CIFS style: //server/share
        result["address"] = source
        return result

    # Check for device paths
    if source.startswith("/dev/"):
        result["path"] = source
        return result

    # Check for other absolute paths (bind mounts, etc.)
    if source.startswith("/"):
        result["path"] = source
        return result

    # Everything else is likely a special filesystem name
    # (proc, sysfs, tmpfs, devpts, etc.)
    result["name"] = source
    return result
