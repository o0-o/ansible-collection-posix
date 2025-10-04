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

from typing import Any, Dict, List, Union

from ansible_collections.o0_o.posix.plugins.module_utils.jc_utils import (
    jc_parse,
)

VALID_KEYS = {"id", "name"}


def id_info(
    config: Union[str, Dict[str, Any]], key: str = "id"
) -> Dict[str, Any]:
    """Normalize ``id`` command output for user/group lookups."""

    if key not in VALID_KEYS:
        raise ValueError(f"Unsupported key '{key}', expected 'id' or 'name'")

    parsed: Dict[str, Any] | List[Dict[str, Any]] | Dict[str, Any]
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

    users: Dict[str, Any] = {}
    groups: Dict[str, Any] = {}

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


def _unique_int_list(values: List[int | None]) -> List[int]:
    result: List[int] = []
    for value in values:
        if value is None or value in result:
            continue
        result.append(value)
    return result


def _unique_str_list(values: List[str | None]) -> List[str]:
    result: List[str] = []
    for value in values:
        if value is None:
            continue
        if value not in result:
            result.append(value)
    return result


__all__ = ["id_info"]
