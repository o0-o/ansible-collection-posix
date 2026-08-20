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

"""Utilities for parsing ``id`` command output."""

from __future__ import annotations

from typing import Any, Optional, Union

from ansible_collections.o0_o.core.plugins.module_utils import (
    process_all_command_results,
    process_command_spec,
)

from ansible_collections.o0_o.posix.plugins.module_utils.jc_utils import (
    jc_parse,
)

VALID_KEYS = {"id", "name"}


def _parse_effective_uid(
    output: str,
    e_prefix: str,
) -> tuple[Optional[int], Optional[list[Exception]]]:
    """Canonical COMMAND_SPEC parser for ``id -u``.

    :param str output: Raw stdout (e.g. ``1000``)
    :param str e_prefix: Error prefix for context
    :returns tuple[Optional[int], Optional[list[Exception]]]: The
        effective UID and list of errors
    """
    text = (output or "").strip()
    uid = _to_int(text)
    if uid is None:
        return None, [ValueError(f"{e_prefix}uid is not numeric: {text!r}")]
    return uid, None


def get_effective_uid_command_requests() -> list[dict[str, Any]]:
    """Build the command request for the effective user's UID.

    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (  # noqa: E501
        ID_COMMAND_SPEC,
    )

    return process_command_spec(ID_COMMAND_SPEC, cmd_type="effective_uid")


def process_effective_uid_results(
    cmds_completed: list[dict[str, Any]],
) -> Optional[int]:
    """Extract the effective UID from command results.

    :param list[dict[str, Any]] cmds_completed: Command results from
        run plugin
    :returns Optional[int]: The effective UID, or None when ``id -u``
        did not answer
    """
    processed = process_all_command_results(cmds_completed)

    result = processed.get("effective_uid")
    if isinstance(result, list):
        result = result[0] if result else None
    if not isinstance(result, dict):
        return None

    parsed = result.get("parsed")
    return parsed if isinstance(parsed, int) else None


def id_info(
    config: Union[str, dict[str, Any]], key: str = "id"
) -> dict[str, Any]:
    """Normalize ``id`` command output for user/group lookups."""

    if key not in VALID_KEYS:
        raise ValueError(f"Unsupported key '{key}', expected 'id' or 'name'")

    parsed: dict[str, Any] | list[dict[str, Any]] | dict[str, Any]
    if isinstance(config, dict):
        if "stdout" in config or "content" in config:
            parsed = jc_parse("id", config)
        elif any(key in config for key in ("uid", "gid", "groups")):
            parsed = config
        else:
            return {"users": {}, "groups": {}}
    elif isinstance(config, list):
        if (
            config
            and isinstance(config[0], dict)
            and any(key in config[0] for key in ("uid", "gid", "groups"))
        ):
            parsed = config
        else:
            parsed = jc_parse("id", config)
    else:
        parsed = jc_parse("id", config)

    if isinstance(parsed, list):
        data = parsed[0] if parsed else {}
    else:
        data = parsed or {}

    users: dict[str, Any] = {}
    groups: dict[str, Any] = {}

    uid_info = data.get("uid") or {}
    gid_info = data.get("gid") or {}
    group_list = data.get("groups") or []

    primary_id = _to_int(uid_info.get("id"))
    primary_name = uid_info.get("name") or None
    primary_gid_id = _to_int(gid_info.get("id"))
    primary_gid_name = gid_info.get("name") or None

    if key == "id":
        if primary_id is not None:
            users[str(primary_id)] = {
                "name": primary_name,
                "group": primary_gid_id,
                "groups": _unique_int_list(
                    [_to_int(grp.get("id")) for grp in group_list]
                ),
            }

        if primary_gid_id is not None and str(primary_gid_id) not in groups:
            groups[str(primary_gid_id)] = {"name": primary_gid_name}

        for group in group_list:
            gid = _to_int(group.get("id"))
            if gid is None:
                continue
            groups.setdefault(str(gid), {"name": group.get("name")})

    else:  # key == "name"
        if primary_name:
            users[primary_name] = {
                "id": primary_id,
                "group": (
                    primary_gid_name
                    if primary_gid_name
                    else (
                        _stringify(primary_gid_id)
                        if primary_gid_id is not None
                        else None
                    )
                ),
                "groups": _unique_str_list(
                    [
                        (
                            group.get("name")
                            if group.get("name")
                            else _stringify(_to_int(group.get("id")))
                        )
                        for group in group_list
                    ]
                ),
            }

        if primary_gid_name:
            groups.setdefault(primary_gid_name, {"id": primary_gid_id})
        elif primary_gid_id is not None:
            groups.setdefault(str(primary_gid_id), {"id": primary_gid_id})

        for group in group_list:
            name = group.get("name")
            gid = _to_int(group.get("id"))
            if name:
                groups.setdefault(name, {"id": gid})
            elif gid is not None:
                groups.setdefault(str(gid), {"id": gid})

    return {"users": users, "groups": groups}


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _stringify(value: int | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _unique_int_list(values: list[int | None]) -> list[int]:
    result: list[int] = []
    for value in values:
        if value is None or value in result:
            continue
        result.append(value)
    return result


def _unique_str_list(values: list[str | None]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        if value not in result:
            result.append(value)
    return result


__all__ = [
    "get_effective_uid_command_requests",
    "id_info",
    "process_effective_uid_results",
]
