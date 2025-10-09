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

"""Utilities for parsing SSH ``authorized_keys`` file content."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Union

# Valid SSH key types
VALID_KEY_TYPES = {
    "ssh-rsa",
    "ssh-dss",
    "ssh-ed25519",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "sk-ecdsa-sha2-nistp256@openssh.com",
    "sk-ssh-ed25519@openssh.com",
}

# Pattern to match authorized_keys options
OPTIONS_PATTERN = re.compile(
    r'^(?:'
    r'(?:cert-authority|command|environment|expiry-time|from|'
    r'no-agent-forwarding|no-port-forwarding|no-pty|no-user-rc|'
    r'no-X11-forwarding|permitlisten|permitopen|'
    r'port-forwarding|principals|pty|restrict|tunnel|user-rc|'
    r'X11-forwarding)'
    r'(?:="[^"]*")?'
    r'(?:,|$))'
)


def parse_authorized_keys_entry(line: str) -> Dict[str, Any] | None:
    """Parse a single authorized_keys entry.

    The SSH authorized_keys format is:
    [options] key-type base64-key [comment]

    :param str line: A single line from authorized_keys file
    :returns Dict[str, Any] | None: Parsed entry or None for invalid
        lines
    """
    line = line.strip()

    # Skip empty lines and comments
    if not line or line.startswith("#"):
        return None

    # Split into parts, but preserve spaces in comment at the end
    # First, find the key type
    parts = line.split()
    if len(parts) < 2:
        return None

    # Try to identify where the key type starts
    key_type_idx = -1
    for i, part in enumerate(parts):
        if part in VALID_KEY_TYPES:
            key_type_idx = i
            break

    if key_type_idx == -1:
        # No valid key type found
        return None

    if key_type_idx >= len(parts) - 1:
        # Need at least key type and key data
        return None

    key_type = parts[key_type_idx]
    key_data = parts[key_type_idx + 1]

    # Everything before key type is options
    options_str = None
    if key_type_idx > 0:
        options_str = " ".join(parts[:key_type_idx])

    # Everything after key data is the comment
    # Need to find it in original line to preserve spaces
    comment = None
    if len(parts) > key_type_idx + 2:
        # Find position in original line after key_data
        key_data_pos = line.find(key_data)
        after_key = line[key_data_pos + len(key_data):].lstrip()
        if after_key:
            comment = after_key

    result: Dict[str, Any] = {
        "type": key_type,
        "key": key_data,
    }

    if comment:
        result["comment"] = comment

    if options_str:
        result["options"] = parse_key_options(options_str)

    return result


def parse_key_options(options_str: str) -> List[Dict[str, Any]]:
    """Parse SSH key options string.

    Options are comma-separated and may have values:
    - Simple flags: no-port-forwarding
    - Key-value pairs: from="*.example.com"

    :param str options_str: The options string to parse
    :returns List[Dict[str, Any]]: List of parsed option dictionaries
    """
    options: List[Dict[str, Any]] = []
    current_pos = 0
    options_str = options_str.strip()

    while current_pos < len(options_str):
        # Find next comma (but not inside quotes)
        in_quotes = False
        next_comma = -1
        for i in range(current_pos, len(options_str)):
            if options_str[i] == '"':
                in_quotes = not in_quotes
            elif options_str[i] == "," and not in_quotes:
                next_comma = i
                break

        if next_comma == -1:
            # No more commas, take rest of string
            option_str = options_str[current_pos:].strip()
            current_pos = len(options_str)
        else:
            option_str = options_str[current_pos:next_comma].strip()
            current_pos = next_comma + 1

        if not option_str:
            continue

        # Parse the option
        if "=" in option_str:
            key, value = option_str.split("=", 1)
            # Remove quotes from value
            value = value.strip('"')
            options.append({"name": key.strip(), "value": value})
        else:
            options.append({"name": option_str, "value": None})

    return options


def parse_authorized_keys(
    content: Union[str, List[str]]
) -> List[Dict[str, Any]]:
    """Parse authorized_keys file content into structured data.

    :param Union[str, List[str]] content: File content as string or list
        of lines
    :returns List[Dict[str, Any]]: List of parsed key entries
    """
    if isinstance(content, str):
        lines = content.splitlines()
    else:
        lines = content

    entries: List[Dict[str, Any]] = []
    for line in lines:
        entry = parse_authorized_keys_entry(line)
        if entry:
            entries.append(entry)

    return entries


def authorized_keys(
    data: Union[str, Dict[str, Any], List[Dict[str, Any]]]
) -> List[Dict[str, Any]]:
    """Parse authorized_keys content from various input formats.

    Accepts:
    - Raw file content as string
    - Command result dict with 'stdout' key
    - Slurp result dict with 'content' key (base64)
    - Pre-parsed list of entries

    :param Union[str, Dict[str, Any], List[Dict[str, Any]]] data: Input
        data in various formats
    :returns List[Dict[str, Any]]: List of parsed key entries
    """
    import base64

    # Handle pre-parsed list
    if isinstance(data, list):
        if data and isinstance(data[0], dict) and "type" in data[0]:
            # Already parsed
            return data
        # List of lines
        return parse_authorized_keys(data)

    # Handle dict (command result or slurp result)
    if isinstance(data, dict):
        # Check if it's empty or doesn't have stdout/content
        if not data or ("stdout" not in data and "content" not in data):
            return []

        if "stdout" in data:
            # Command result - use stdout directly
            return parse_authorized_keys(data["stdout"])
        elif "content" in data:
            # Slurp result - decode base64
            try:
                decoded = base64.b64decode(data["content"]).decode("utf-8")
                return parse_authorized_keys(decoded)
            except Exception:
                # Try parsing as-is if decode fails
                return parse_authorized_keys(data["content"])

    # Handle raw string
    if isinstance(data, str):
        return parse_authorized_keys(data)

    return []


__all__ = [
    "authorized_keys",
    "parse_authorized_keys",
    "parse_authorized_keys_entry",
    "parse_key_options",
]
