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

# Mapping from environment variable names to human-readable keys
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


def _parse_assignments(
    text: str,
) -> dict[str, str]:
    """Parse KEY=VALUE lines into a dictionary.

    :param str text: Text containing KEY=VALUE lines
    :returns dict[str, str]: Mapping of keys to values with
        quotes stripped
    """
    data = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"')
        if key:
            data[key] = value
    return data


def _map_locale_vars(
    env_data: dict[str, str],
) -> dict[str, Any]:
    """Map locale environment variables to category names.

    :param dict[str, str] env_data: Raw locale env vars
    :returns dict[str, Any]: Mapped locale categories
    """
    result = {v: None for v in LOCALE_MAPPING.values()}
    for env_key, category in LOCALE_MAPPING.items():
        value = env_data.get(env_key)
        if value:
            result[category] = value
    return result


def _parse_locale(
    output: str,
    e_prefix: str,
) -> tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
    """Canonical COMMAND_SPEC parser for locale command output.

    Parses KEY=VALUE output from the ``locale`` command into
    structured locale categories.

    :param str output: Raw stdout from ``locale``
    :param str e_prefix: Error prefix for context
    :returns tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
        Parsed locale data and list of errors
    """
    errors = []
    text = (output or "").strip()
    if not text:
        errors.append(ValueError(f"{e_prefix}Empty locale output"))
        return None, errors

    env_data = _parse_assignments(text)
    if not env_data:
        errors.append(
            ValueError(f"{e_prefix}No KEY=VALUE pairs in locale output")
        )
        return None, errors

    return _map_locale_vars(env_data), errors


def _parse_locale_env(
    output: str,
    e_prefix: str,
) -> tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
    """COMMAND_SPEC parser for env command output (locale fallback).

    Parses full ``env`` output but extracts only locale-related
    variables.

    :param str output: Raw stdout from ``env``
    :param str e_prefix: Error prefix for context
    :returns tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
        Parsed locale data and list of errors
    """
    errors = []
    text = (output or "").strip()
    if not text:
        errors.append(ValueError(f"{e_prefix}Empty env output"))
        return None, errors

    env_data = _parse_assignments(text)
    # Filter to only locale-relevant keys
    locale_data = {k: v for k, v in env_data.items() if k in LOCALE_MAPPING}
    if not locale_data:
        errors.append(
            ValueError(f"{e_prefix}No locale variables in env output")
        )
        return None, errors

    return _map_locale_vars(locale_data), errors


def get_locale_command_requests() -> list[dict[str, Any]]:
    """Build command requests for locale fact gathering.

    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (  # noqa: E501
        LOCALE_COMMAND_SPEC,
    )

    return process_command_spec(LOCALE_COMMAND_SPEC)


def process_locale_command_results(
    cmds_completed: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[Exception]]:
    """Process locale command results into structured facts.

    Prefers ``locale`` command output over ``env`` fallback.

    :param list[dict[str, Any]] cmds_completed: List of command
        result dicts from run plugin
    :returns tuple[dict[str, Any], list[Exception]]: Tuple of
        (facts_dict, errors) where facts_dict has o0_os namespace
    """
    processed = process_all_command_results(cmds_completed)
    errors = []

    # Prefer locale command over env fallback
    locale_result = processed.get("locale")
    if locale_result and locale_result.get("parsed"):
        errors.extend(locale_result.get("errors", []))
        return (
            {"o0_os": {"locale": locale_result["parsed"]}},
            errors,
        )

    # Fall back to env
    env_result = processed.get("locale_env")
    if env_result and env_result.get("parsed"):
        errors.extend(env_result.get("errors", []))
        return (
            {"o0_os": {"locale": env_result["parsed"]}},
            errors,
        )

    # Both failed
    if locale_result:
        errors.extend(locale_result.get("errors", []))
    if env_result:
        errors.extend(env_result.get("errors", []))
    if not errors:
        errors.append(ValueError("No locale data from locale or env"))

    return {}, errors
