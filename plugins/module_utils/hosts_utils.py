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

"""Hosts file parsing and generation utilities."""

from __future__ import annotations

from typing import Any, Dict, List, Union

from ansible_collections.o0_o.posix.plugins.module_utils.jc_utils import (
    jc_parse,
)


def parse_hosts_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a single hosts entry from jc output to normalized format.

    Converts jc's hosts field names to standardized format:
    - ip → address
    - hostname → hostnames (list with primary hostname and aliases)

    :param Dict[str, Any] entry: Single hosts entry from jc parser
    :returns Dict[str, Any]: Normalized entry dict
    :raises ValueError: If required fields are missing
    """
    if not entry:
        raise ValueError("Empty hosts entry")

    norm_entry = {}

    # Required field: IP address
    if "ip" not in entry:
        raise ValueError("Missing ip in hosts entry")

    norm_entry["address"] = entry["ip"]

    # Hostname field from jc is a list of [hostname, alias1, alias2, ...]
    if "hostname" in entry and entry["hostname"]:
        hostnames = entry["hostname"]
        if isinstance(hostnames, list):
            norm_entry["hostnames"] = hostnames
        else:
            # Single hostname
            norm_entry["hostnames"] = [hostnames]
    else:
        norm_entry["hostnames"] = []

    return norm_entry


def generate_hosts_entry(entry: Dict[str, Any]) -> str:
    """Generate a hosts file line from a normalized entry dict.

    Converts normalized format back to hosts line:
    - address → IP address
    - hostnames → list of hostnames (primary + aliases)

    :param Dict[str, Any] entry: Normalized entry dict
    :returns str: Formatted hosts line
    :raises ValueError: If required fields are missing
    """
    if not entry:
        raise ValueError("Empty hosts entry")

    # Required fields
    if "address" not in entry:
        raise ValueError("Missing address in hosts entry")
    if "hostnames" not in entry or not entry["hostnames"]:
        raise ValueError("Missing hostnames in hosts entry")

    address = entry["address"]
    hostnames_list = entry["hostnames"]

    # Join all hostnames with spaces
    hostnames_str = " ".join(hostnames_list)

    # Format: IP_ADDRESS    HOSTNAME [ALIASES...]
    # Use tab separator for better alignment
    return f"{address}\t{hostnames_str}"


def hosts(
    config: Union[str, Dict[str, Any], List[Dict[str, Any]]],
) -> Union[List[Dict[str, Any]], str]:
    """Process hosts data - parse or generate based on input type.

    Bidirectional processor that either:
    1. Parses hosts file text into normalized list of entries
    2. Generates hosts file text from list of entries

    For parsing (string input):
    - ip → address
    - hostname → hostnames (list with primary + aliases)

    For generation (list of dicts input):
    - address → IP address
    - hostnames → list of hostnames (primary + aliases)

    :param config: Hosts text to parse or list of entries to generate
    :returns: Either parsed entries list or generated hosts text
    :raises ValueError: If parsing or generation fails
    :raises ImportError: If jc is not available
    """
    # Check if this is a list input
    if isinstance(config, list):
        # Check if list contains dicts (for generation) or strings (for parsing)
        if config and isinstance(config[0], dict):
            # Generate hosts file from list of entries
            lines = []
            for entry in config:
                line = generate_hosts_entry(entry)
                lines.append(line)
            return "\n".join(lines) + "\n"
        else:
            # List of strings - convert to single string for parsing
            content = "\n".join(config)
    # Handle dict input (from slurp or command result)
    elif isinstance(config, dict):
        # Try common keys for file content
        if "content" in config:
            content = config["content"]
        elif "stdout" in config:
            content = config["stdout"]
        else:
            raise ValueError(
                "Dict input must have 'content' or 'stdout' key"
            )
    else:
        # String input
        content = config

    # Parse using jc
    raw_entries = jc_parse("hosts", content)

    # Normalize each entry
    normalized = []
    for entry in raw_entries:
        try:
            norm_entry = parse_hosts_entry(entry)
            normalized.append(norm_entry)
        except ValueError as e:
            # Skip invalid entries
            continue

    return normalized
