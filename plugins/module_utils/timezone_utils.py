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

"""System timezone detection utilities.

Queries the system-level timezone by unsetting TZ and running
``date``, which forces the implementation-defined default.
"""

from __future__ import annotations

from datetime import timedelta, timezone
from typing import Any, Optional

from ansible_collections.o0_o.core.plugins.module_utils import (
    process_all_command_results,
    process_command_spec,
)

from ansible_collections.o0_o.core.plugins.module_utils.evidence_utils import (  # noqa: E501
    commands_run,
    compose_evidence,
    name_origins,
)

# What this module is called, which is what a fact it composes
# names as one of the producers that made it
FQCN = "o0_o.posix.timezone"


def parse_timezone_offset(offset: str) -> timezone:
    """Parse a UTC offset string like '-0400' or '+0530'.

    The format is what ``date +%z`` prints: a sign followed by four
    digits, hours then minutes.

    :param str offset: Timezone offset string from ``date +%z``
    :returns timezone: Timezone object with the specified offset
    :raises ValueError: If the offset format is invalid
    """
    if len(offset) != 5 or offset[0] not in ("+", "-"):
        raise ValueError(f"Invalid offset format: {offset}")

    try:
        sign = 1 if offset[0] == "+" else -1
        hours = int(offset[1:3])
        minutes = int(offset[3:5])
    except ValueError:
        raise ValueError(f"Invalid offset format: {offset}")

    offset_delta = timedelta(hours=sign * hours, minutes=sign * minutes)
    return timezone(offset_delta)


def _parse_timezone(
    output: str,
    e_prefix: str,
) -> tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
    """Canonical COMMAND_SPEC parser for system timezone.

    Parses output from ``unset TZ; date "+%Z %z"`` into a dict
    with abbreviation and UTC offset.

    :param str output: Raw stdout (e.g. ``EST -0500``)
    :param str e_prefix: Error prefix for context
    :returns tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
        Parsed timezone data and list of errors
    """
    errors = []
    text = (output or "").strip()
    if not text:
        errors.append(ValueError(f"{e_prefix}Empty timezone output"))
        return None, errors

    parts = text.split()
    result = {}

    if parts:
        result["abbreviation"] = parts[0]
    if len(parts) > 1:
        result["offset"] = parts[1]

    if not result:
        errors.append(
            ValueError(f"{e_prefix}Could not parse timezone: {text}")
        )
        return None, errors

    return result, errors


def get_timezone_command_requests() -> list[dict[str, Any]]:
    """Build command requests for system timezone detection.

    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (  # noqa: E501
        TIMEZONE_COMMAND_SPEC,
    )

    return process_command_spec(TIMEZONE_COMMAND_SPEC)


def process_timezone_command_results(
    cmds_completed: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[Exception]]:
    """Process timezone command results into structured facts.

    The namespace names what was consulted for it, so a gather that
    read the clock and a gather that read the standards both say
    which commands answered for the o0_os facts they published.

    :param list[dict[str, Any]] cmds_completed: Command results
    :returns tuple[dict[str, Any], list[Exception]]: Tuple of
        (facts_dict, errors) where facts_dict has o0_os namespace
    """
    processed = process_all_command_results(cmds_completed)
    errors = []

    tz_result = processed.get("timezone")
    if tz_result is None:
        return {}, [ValueError("No timezone result found")]

    errors.extend(tz_result.get("errors", []))
    tz_data = tz_result.get("parsed")

    if not tz_data:
        return {}, errors

    return name_origins(
        {
            "o0_os": {
                "timezone": tz_data,
                "evidence": compose_evidence(
                    commands=commands_run(cmds_completed, "timezone")
                ),
            }
        },
        FQCN,
    ), errors
