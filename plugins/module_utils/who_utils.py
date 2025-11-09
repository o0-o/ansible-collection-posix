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

"""Helpers for parsing who command output."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

try:
    from dateutil import parser as dateutil_parser
except ImportError:  # pragma: no cover - handled by parse_datetime import
    dateutil_parser = None

from ansible_collections.o0_o.posix.plugins.module_utils import jc_parse
from ansible_collections.o0_o.utils.plugins.module_utils import (
    parse_datetime,
    parse_elapsed_time,
)


def _coerce_to_text(data: Union[str, Sequence[str], Dict[str, Any]]) -> str:
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        if "stdout" in data and isinstance(data["stdout"], str):
            return data["stdout"]
        if "content" in data and isinstance(data["content"], str):
            return data["content"]
        return "\n".join(str(value) for value in data.values())
    if isinstance(data, Iterable):
        return "\n".join(str(item) for item in data)
    return ""


def parse_who(
    data: Union[str, Sequence[str], Dict[str, Any]],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Parse who command output into structured session data."""
    text = _coerce_to_text(data).strip()
    if not text:
        raise ValueError("who output is empty")

    try:
        parsed = jc_parse("who", data)
    except Exception as exc:
        raise ValueError(f"failed to parse who output: {exc}") from exc

    entries = parsed if isinstance(parsed, list) else [parsed]
    sessions: List[Dict[str, Any]] = []
    reference_time = _resolve_reference_time(now)

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        user = entry.get("user")
        tty = entry.get("line") or entry.get("tty")
        host = entry.get("host") or entry.get("ip_address")
        login_raw = entry.get("time") or entry.get("datetime") or ""
        login_dt = _normalise_login_datetime(login_raw, reference_time)
        # Preserve timezone information in output while epoch remains correct
        login_info = parse_datetime(login_dt.isoformat())
        elapsed_info = _compute_elapsed(reference_time, login_dt)

        session: Dict[str, Any] = {}
        if user:
            session["user"] = user
        if tty:
            session["tty"] = tty
        if host:
            session["host"] = host
        if login_info:
            session["login_at"] = login_info
        if elapsed_info:
            session["elapsed"] = elapsed_info
        pid = entry.get("pid")
        if pid is not None:
            session["pid"] = pid

        sessions.append(session)

    if not sessions:
        raise ValueError("no session entries found in who output")

    return {"sessions": sessions}


def _normalise_login_datetime(value: str, reference: datetime) -> datetime:
    candidate = (value or "").strip()
    if candidate:
        info = parse_datetime(candidate)
        resolved = _datetime_from_info(candidate, info, reference)
        if resolved is not None:
            return resolved.replace(microsecond=0)
    return reference.replace(microsecond=0)


def _datetime_from_info(
    candidate: str,
    info: Optional[Dict[str, Any]],
    reference: datetime,
) -> Optional[datetime]:
    tzinfo = reference.tzinfo or timezone.utc
    if info:
        iso_value = info.get("iso8601")
        if iso_value:
            iso_value = iso_value.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(iso_value)
            except ValueError:
                dt = None
            else:
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=tzinfo)
                else:
                    dt = dt.astimezone(tzinfo)
                return dt
        return _parse_with_dateutil(candidate, reference, iso_value)
    return _parse_with_dateutil(candidate, reference, None)


def _parse_with_dateutil(
    candidate: str,
    reference: datetime,
    iso_hint: Optional[str],
) -> Optional[datetime]:
    if dateutil_parser is None:
        return None

    # Zero out seconds and microseconds for default so times without
    # seconds (e.g., "Oct 16 11:03") default to :00 not reference seconds
    default_dt = reference.replace(second=0, microsecond=0)
    try:
        parsed = dateutil_parser.parse(
            candidate, fuzzy=False, default=default_dt
        )
    except Exception:
        return None

    tzinfo = reference.tzinfo or timezone.utc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tzinfo)
    parsed = parsed.astimezone(tzinfo)

    tolerance = timedelta(minutes=5)

    if iso_hint:
        if iso_hint.startswith("--"):
            for attempt in range(3):
                if parsed <= reference + tolerance:
                    break
                try:
                    parsed = parsed.replace(year=parsed.year - 1)
                except ValueError:
                    parsed = parsed - timedelta(days=366)
        elif ":" in iso_hint and "T" not in iso_hint and "-" not in iso_hint:
            if parsed > reference + tolerance:
                parsed = parsed - timedelta(days=1)

    return parsed


def _compute_elapsed(reference: datetime, start: datetime) -> Dict[str, Any]:
    if start > reference:
        start = reference
    seconds = int((reference - start).total_seconds())
    info = parse_elapsed_time(_format_elapsed(seconds))
    if info is None:
        return {"seconds": seconds, "iso8601": f"PT{seconds}S", "pretty": ""}
    return info


def _format_elapsed(seconds: int) -> str:
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    time_part = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    if days:
        return f"{days}-{time_part}"
    return time_part


def _resolve_reference_time(reference: Optional[datetime]) -> datetime:
    if reference is None:
        return datetime.now(timezone.utc)
    if reference.tzinfo is None:
        return reference.replace(tzinfo=timezone.utc)
    return reference


__all__ = ["parse_who"]
