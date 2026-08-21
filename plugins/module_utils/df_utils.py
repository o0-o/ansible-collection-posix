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

from typing import Any, Optional, Union

from ansible_collections.o0_o.posix.plugins.module_utils.filter_utils import (
    decode_declared_content,
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


def _realign_df(content: str) -> Optional[str]:
    """Re-render a df table whose rows overflow their header columns.

    jc reads df by slicing every line at the header's column
    positions, and a row wider than the header defeats that slice. A
    filesystem name running past the Filesystem column is swapped for
    a shorter hash, which slides each later field left of the column
    it belongs to; a capacity running past its own column swallows the
    mount point. Fields jc cannot place come back as null, and jc's
    own numeric conversion raises on them before the parse returns.

    POSIX guarantees df -P prints one line per filesystem with the
    mount point last, so the fields of a misread row are its
    whitespace separated tokens, the final column taking any
    remainder. The table is re-rendered from those fields, one column
    per header name and wide enough that jc's slice lands on a
    separator. Rows jc placed correctly keep the values it read, so a
    field holding a space, such as an automounter map name or a mount
    point with a space in it, survives the round trip. A row with
    fewer fields than the header has columns cannot be placed at all
    and raises.

    :param content: Df output as string
    :returns: Re-rendered table, or None if jc placed every field
    :raises ValueError: If a row does not split into the header's
                        columns
    :raises ImportError: If jc is not available
    """
    lines = [ln for ln in content.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None

    raw = jc_parse("df", content, raw=True)
    if len(raw) != len(lines) - 1:
        return None

    columns = list(raw[0].keys())
    rows: list[list[str]] = []
    misread = False

    for entry, line in zip(raw, lines[1:]):
        values = [entry.get(column) for column in columns]
        fields = line.split()
        placed = None not in values and fields == [
            token for value in values for token in str(value).split()
        ]
        if placed:
            rows.append([str(value) for value in values])
            continue
        if len(fields) < len(columns):
            raise ValueError(f"Unparseable df row: {line!r}")
        misread = True
        last = len(columns) - 1
        rows.append(fields[:last] + [" ".join(fields[last:])])

    if not misread:
        return None

    widths = [
        max(len(column), *(len(row[index]) for row in rows))
        for index, column in enumerate(columns)
    ]
    return "\n".join(
        "  ".join(
            cell.ljust(width) for cell, width in zip(cells, widths)
        ).rstrip()
        for cells in [columns] + rows
    )


def parse_df(content: str) -> list[dict[str, Any]]:
    """Parse df output into normalized list of entries.

    :param content: Df output as string
    :returns: List of normalized entry dicts
    :raises ValueError: If parsing fails
    :raises ImportError: If jc is not available
    """
    # Parse with jc_parse, from a re-rendered table when jc's
    # positional read of this output loses fields
    realigned = _realign_df(content)
    parsed = jc_parse("df", content if realigned is None else realigned)

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


def _parse_df(
    output: str,
    e_prefix: str,
) -> tuple[Optional[list[dict[str, Any]]], Optional[list[Exception]]]:
    """Canonical COMMAND_SPEC parser for ``df -P`` output.

    :param str output: Raw stdout from ``df -P``
    :param str e_prefix: Error prefix for context
    :returns tuple[Optional[list[dict[str, Any]]], Optional[list[Exception]]]:
        Parsed df entries and list of errors
    """
    errors: list[Exception] = []
    text = (output or "").strip()
    if not text:
        errors.append(ValueError(f"{e_prefix}Empty df output"))
        return None, errors

    try:
        parsed = parse_df(text)
    except Exception as e:
        errors.append(ValueError(f"{e_prefix}Failed to parse df: {e}"))
        return None, errors

    return parsed, errors


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
            # A read or slurp result declares an encoded content
            declared = decode_declared_content(
                content, config.get("encoding")
            )
            if declared is not None:
                content = declared
        else:
            raise ValueError("Dict input must have 'stdout' or 'content' key")
    else:
        content = config

    return parse_df(str(content))
