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

"""Df parsing utilities."""

from __future__ import annotations

import base64

from typing import Any, Union

from ansible_collections.o0_o.posix.plugins.module_utils.filter_utils import (
    normalize_source,
)
from ansible_collections.o0_o.posix.plugins.module_utils.jc_utils import (
    jc_parse,
)

try:
    from ansible_collections.o0_o.utils.plugins.module_utils import parse_si

    HAS_PARSE_SI = True
except ImportError:
    parse_si = None
    HAS_PARSE_SI = False


def parse_df_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Parse a single df entry from jc output to normalized format.

    Converts jc's df field names to standardized format:
    - filesystem → source
    - mounted_on → mount
    - Builds capacity structure with total/used (bytes, pretty, percent)

    :param entry: Single df entry from jc parser
    :returns: Normalized entry dict with capacity
    :raises ValueError: If required fields are missing
    """
    if not entry:
        raise ValueError("Empty df entry")

    norm_entry = {}

    # Required fields
    if "mounted_on" not in entry:
        raise ValueError("Missing mounted_on in df entry")

    norm_entry["mount"] = entry["mounted_on"]

    # Source (filesystem)
    if "filesystem" in entry:
        norm_entry["source"] = normalize_source(entry["filesystem"])

    # Build capacity structure if we have parse_si
    if HAS_PARSE_SI and parse_si:
        # Find block size and total from field names like 1024_blocks,
        # 512_blocks
        block_size = None
        total_blocks = None
        for key in entry.keys():
            if key.endswith("_blocks"):
                # Total is the value in this blocks field
                total_blocks = entry[key]
                # Extract the block size
                block_size_str = key.replace("_blocks", "")
                if block_size_str.isdigit():
                    block_size = int(block_size_str)
                break

        capacity = {}

        # Process total
        if total_blocks is not None and block_size:
            # Convert blocks to bytes
            total_bytes = total_blocks * block_size
            si_result = parse_si(f"{total_bytes}B", binary=True)
            capacity["total"] = {
                "bytes": si_result.get("bytes", total_bytes),
                "pretty": si_result.get("pretty", f"{total_bytes}B"),
            }
        elif "size" in entry:
            # Size field already has units
            si_result = parse_si(str(entry["size"]), binary=True)
            capacity["total"] = {
                "bytes": si_result.get("bytes", 0),
                "pretty": si_result.get("pretty", str(entry["size"])),
            }

        # Process used
        if "used" in entry:
            if block_size and isinstance(entry["used"], int):
                # Used is in blocks
                used_bytes = entry["used"] * block_size
                si_result = parse_si(f"{used_bytes}B", binary=True)
                capacity["used"] = {
                    "bytes": si_result.get("bytes", used_bytes),
                    "pretty": si_result.get("pretty", f"{used_bytes}B"),
                }
            else:
                # Used already has units
                si_result = parse_si(str(entry["used"]), binary=True)
                capacity["used"] = {
                    "bytes": si_result.get("bytes", 0),
                    "pretty": si_result.get("pretty", str(entry["used"])),
                }

        # Calculate percentage if we have both total and used
        # Don't use the percent from df, calculate it ourselves
        if "total" in capacity and "used" in capacity:
            total_bytes = capacity["total"]["bytes"]
            used_bytes = capacity["used"]["bytes"]
            if total_bytes > 0:
                percent = (used_bytes / total_bytes) * 100
                capacity["used"]["percent"] = round(percent, 2)
            else:
                capacity["used"]["percent"] = 0.0

        if capacity:
            norm_entry["capacity"] = capacity

    return norm_entry


def parse_df(content: str) -> list[dict[str, Any]]:
    """Parse df output into normalized list of entries.

    :param content: Df output as string
    :returns: List of normalized entry dicts
    :raises ValueError: If parsing fails
    :raises ImportError: If jc is not available
    """
    # Parse with jc_parse
    parsed = jc_parse("df", content)

    # jc slices df columns by header position, and busybox's df -P
    # rows can overflow their columns, nulling fields jc could not
    # place. POSIX guarantees df -P one line per filesystem with the
    # mount point last, so a whitespace re-split of the source line
    # recovers what the sliced read lost.
    lines = [ln for ln in content.splitlines() if ln.strip()][1:]
    if len(lines) == len(parsed):
        for entry, line in zip(parsed, lines):
            if entry.get("mounted_on") is None:
                fields = line.split()
                if len(fields) >= 6:
                    entry["mounted_on"] = " ".join(fields[5:])

    # Normalize each entry
    normalized = []
    for entry in parsed:
        try:
            norm_entry = parse_df_entry(entry)
            normalized.append(norm_entry)
        except ValueError:
            # Skip invalid entries
            continue

    return normalized


def df(config: Union[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Process df data - parse command output into structured format.

    Returns data structure with:
    - source: filesystem source
    - mount: mount point path
    - capacity: dict with total/used containing bytes and pretty fields

    :param config: Df command output as string or dict
    :returns: List of df entries with capacity structure
    :raises ValueError: If parsing fails
    :raises ImportError: If jc is not available
    """
    if isinstance(config, dict):
        if "stdout" in config:
            content = config["stdout"]
        elif "content" in config:
            content = config["content"]
            # A slurp result declares its base64 encoding
            if config.get("encoding") == "base64":
                content = base64.b64decode(content).decode("utf-8")
        else:
            raise ValueError("Dict input must have 'stdout' or 'content' key")
    else:
        content = config

    return parse_df(str(content))
