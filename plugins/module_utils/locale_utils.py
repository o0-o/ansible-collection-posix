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

"""Locale parsing utilities.

The canonical parser is ``_parse_locale`` which implements the
COMMAND_SPEC ``(output, e_prefix) -> (parsed, errors)`` contract.
"""

from __future__ import annotations

from typing import Any, Optional

from ansible_collections.o0_o.core.plugins.module_utils import (
    process_all_command_results,
    process_command_spec,
)

# Mapping from POSIX locale variable names to readable keys
LOCALE_MAPPING = {
    "LANG": "language",
    "LC_ALL": "all",
    "LC_CTYPE": "characters",
    "LC_COLLATE": "collation",
    "LC_MESSAGES": "messages",
    "LC_MONETARY": "monetary",
    "LC_NUMERIC": "numeric",
    "LC_TIME": "time",
}


def _parse_locale(
    output: str,
    e_prefix: str,
) -> tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
    """Canonical COMMAND_SPEC parser for locale command output.

    Parses KEY=VALUE output from the ``locale`` command into
    a dict with readable key names.  Empty values become None.

    :param str output: Raw stdout from ``locale``
    :param str e_prefix: Error prefix for context
    :returns tuple[Optional[dict[str, Any]],
        Optional[list[Exception]]]: Parsed locale data and
        list of errors
    """
    errors = []
    text = (output or "").strip()
    if not text:
        errors.append(ValueError(f"{e_prefix}Empty locale output"))
        return None, errors

    # Parse KEY=VALUE lines
    raw = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"')
        if key:
            raw[key] = value

    if not raw:
        errors.append(ValueError(f"{e_prefix}No KEY=VALUE pairs in output"))
        return None, errors

    # Map to readable names, empty strings become None
    result = {}
    for env_key, readable_key in LOCALE_MAPPING.items():
        value = raw.get(env_key)
        if value == "" or value is None:
            result[readable_key] = None
        else:
            result[readable_key] = value

    return result, errors


def get_locale_command_requests() -> list[dict[str, Any]]:
    """Build command requests for locale detection.

    :returns list[dict[str, Any]]: Command requests for run
        plugin
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (  # noqa: E501
        LOCALE_COMMAND_SPEC,
    )

    return process_command_spec(LOCALE_COMMAND_SPEC)


def process_locale_command_results(
    cmds_completed: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[Exception]]:
    """Process locale command results into structured data.

    :param list[dict[str, Any]] cmds_completed: Command results
    :returns tuple[dict[str, Any], list[Exception]]: Tuple of
        (locale_dict, errors)
    """
    processed = process_all_command_results(cmds_completed)
    errors = []

    locale_result = processed.get("locale")
    if locale_result and locale_result.get("parsed"):
        errors.extend(locale_result.get("errors", []))
        return locale_result["parsed"], errors

    if locale_result:
        errors.extend(locale_result.get("errors", []))
    if not errors:
        errors.append(ValueError("No locale data from locale command"))

    return {}, errors
