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

"""Helpers for parsing uptime command output."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

from ansible_collections.o0_o.posix.plugins.module_utils.jc_utils import (
    jc_parse,
)
from ansible_collections.o0_o.utils.plugins.module_utils import (
    parse_datetime,
    parse_elapsed_time,
)


def _coerce_to_text(data: Union[str, Sequence[str], Dict[str, Any]]) -> str:
    """Convert supported inputs into a single string."""
    if isinstance(data, str):
        return data

    if isinstance(data, dict):
        if "stdout" in data and isinstance(data["stdout"], str):
            return data["stdout"]
        if "content" in data and isinstance(data["content"], str):
            return data["content"]
        # Fallback to joining values when presented with list-like dict
        return "\n".join(str(value) for value in data.values())

    if isinstance(data, Iterable):
        return "\n".join(str(item) for item in data)

    return ""


def _extract_uptime_segment(rest: str) -> str:
    """Extract the uptime duration portion prior to user/load info."""
    without_load = re.split(r",?\s*load averages?:", rest, maxsplit=1)[0]
    segments = [segment.strip() for segment in without_load.split(",")]

    uptime_parts: List[str] = []
    for segment in segments:
        if not segment:
            continue
        if "user" in segment:
            break
        uptime_parts.append(segment)

    return ", ".join(uptime_parts).strip()


def _parse_elapsed(uptime_text: str) -> int:
    """Convert uptime text into total elapsed seconds."""
    text = uptime_text.lower()
    days = 0
    hours = 0
    minutes = 0
    seconds = 0

    # Days component: "3 days" or "1 day"
    day_match = re.search(r"(\d+)\s+day", text)
    if day_match:
        days = int(day_match.group(1))
        text = re.sub(r"\d+\s+days?,?\s*", " ", text, count=1)

    # Hours:Minutes component e.g. "2:03"
    time_match = re.search(r"(\d+):(\d+)", text)
    if time_match:
        hours = int(time_match.group(1))
        minutes = int(time_match.group(2))
        text = text.replace(time_match.group(0), " ")

    # Minutes component when rendered as "5 mins" or "5 min"
    minute_match = re.search(r"(\d+)\s+min", text)
    if minute_match:
        minutes += int(minute_match.group(1))
        text = text.replace(minute_match.group(0), " ")

    # Seconds component when rendered as "59 secs" or "59 seconds"
    seconds_match = re.search(r"(\d+)\s+sec(?:s|onds)?", text)
    if seconds_match:
        seconds = int(seconds_match.group(1))

    total_seconds = days * 86400 + hours * 3600 + minutes * 60 + seconds

    if total_seconds <= 0:
        raise ValueError(f"Unable to parse uptime duration: '{uptime_text}'")

    return total_seconds


def _extract_load(parsed: Dict[str, Any], text: str) -> List[float]:
    """Determine load averages using jc output or fallback parsing."""

    keys = ("load_1m", "load_5m", "load_15m")
    if all(parsed.get(key) is not None for key in keys):
        return [float(parsed[key]) for key in keys]

    loads = parsed.get("load")
    if isinstance(loads, (list, tuple)) and len(loads) >= 3:
        return [float(loads[i]) for i in range(3)]

    fallback = parsed.get("load_average")
    if isinstance(fallback, (list, tuple)) and len(fallback) >= 3:
        return [float(fallback[i]) for i in range(3)]

    return loads


def _extract_login_sessions(parsed: Dict[str, Any], text: str) -> int:
    """Extract number of logged-in users from parsed uptime data."""

    raw_value = parsed.get("users")

    if isinstance(raw_value, (int, float)):
        return int(raw_value)

    if isinstance(raw_value, str) and raw_value.strip():
        try:
            return int(raw_value.strip())
        except ValueError:
            pass

    match = re.search(r"(\d+)\s+users?", text, re.IGNORECASE)
    if match:
        return int(match.group(1))

    return 0


def _parse_started_time(value: str) -> Optional[Dict[str, Any]]:
    """Parse jc up_since string while dropping microseconds."""

    candidate = value.strip()
    iso_candidate = candidate.replace("Z", "+00:00")

    try:
        dt = datetime.fromisoformat(iso_candidate)
    except ValueError:
        try:
            parsed = parse_datetime(candidate)
        except Exception:
            return None
        iso_value = parsed.get("iso8601")
        if not iso_value:
            return parsed
        try:
            dt = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
        except ValueError:
            return parsed
    dt = dt.replace(microsecond=0)
    return parse_datetime(dt.isoformat())


def parse_uptime(
    data: Union[str, Sequence[str], Dict[str, Any]],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Parse uptime command output into structured data.

    :param data: Raw uptime output (string, list, or command result
        dict)
    :param Optional[datetime] now: Reference time for computing start
        timestamp. Defaults to current UTC time.
    :returns Dict[str, Any]: Parsed uptime details and load averages
        (elapsed uptime and load averages dictionary)
    :raises ValueError: When parsing fails
    """
    text = _coerce_to_text(data).strip()
    if not text:
        raise ValueError("uptime output is empty")

    parsed = jc_parse("uptime", data)
    if isinstance(parsed, list):
        if not parsed:
            raise ValueError("uptime parser returned no data")
        parsed = parsed[0]

    if not isinstance(parsed, dict):
        raise ValueError("unexpected jc uptime result")

    elapsed_seconds = parsed.get("uptime_seconds")

    if elapsed_seconds is None:
        uptime_text = parsed.get("uptime")
        if not uptime_text and " up " in text:
            prefix, remainder = text.split(" up ", 1)
            uptime_text = _extract_uptime_segment(remainder)
        if not uptime_text:
            raise ValueError("could not determine uptime duration")
        elapsed_seconds = _parse_elapsed(uptime_text)

    elapsed_seconds = int(elapsed_seconds)
    if elapsed_seconds <= 0:
        raise ValueError("uptime duration must be positive")

    elapsed_info = parse_elapsed_time(
        _format_elapsed_for_helper(elapsed_seconds)
    )
    if not elapsed_info:
        raise ValueError("failed to normalise elapsed uptime")

    load_values = _extract_load(parsed, text)
    session_count = _extract_login_sessions(parsed, text)

    started_info: Optional[Dict[str, Any]] = None
    up_since = parsed.get("up_since")
    if isinstance(up_since, str) and up_since.strip():
        started_info = _parse_started_time(up_since.strip())

    if not started_info:
        reference_time = _resolve_reference_time(now)
        started_dt = (
            reference_time - timedelta(seconds=elapsed_seconds)
        ).replace(microsecond=0)
        started_info = parse_datetime(started_dt.isoformat())

    return {
        "uptime": {
            "elapsed": elapsed_info,
            "started": started_info,
        },
        "load": {
            "1m": load_values[0],
            "5m": load_values[1],
            "15m": load_values[2],
        },
        "login_sessions": session_count,
    }


def _format_elapsed_for_helper(seconds: int) -> str:
    """Format seconds into ps etime string for parse_elapsed_time."""
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    time_part = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    if days:
        return f"{days}-{time_part}"
    return time_part


def _parse_load_averages(text: str) -> List[float]:
    """Extract load averages from uptime output."""
    load_match = re.search(r"load averages?:\s*(.*)$", text, re.IGNORECASE)
    if not load_match:
        raise ValueError(f"load averages not found in '{text}'")

    load_text = load_match.group(1).strip()
    numbers = re.findall(r"\d+\.\d+|\d+", load_text)
    if len(numbers) < 3:
        raise ValueError(f"expected three load averages, got '{load_text}'")

    return [float(numbers[i]) for i in range(3)]


def _resolve_reference_time(reference: Optional[datetime]) -> datetime:
    """Normalise the reference time to an aware datetime."""
    if reference is None:
        return datetime.now(timezone.utc)
    if reference.tzinfo is None:
        return reference.replace(tzinfo=timezone.utc)
    return reference


__all__ = ["parse_uptime"]
