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

"""Utilities for parsing ``/etc/group`` content."""

from __future__ import annotations

from typing import Any, Dict, List, Union

from ansible_collections.o0_o.posix.plugins.module_utils.jc_utils import jc_parse

VALID_KEYS = {"id", "name"}


def group_info(config: Union[str, Dict[str, Any], List[Dict[str, Any]]], key: str = "id") -> Dict[str, Dict[str, Any]]:
    """Normalize /etc/group data into lookup dictionaries."""

    if key not in VALID_KEYS:
        raise ValueError(f"Unsupported key '{key}', expected 'id' or 'name'")

    entries: List[Dict[str, Any]]

    if isinstance(config, dict):
        if "stdout" in config or "content" in config:
            parsed = jc_parse("etc_group", config)
        elif "gid" in config or "name" in config:
            parsed = [config]
        else:
            return {}
    elif isinstance(config, list):
        if config and isinstance(config[0], dict) and ("gid" in config[0] or "name" in config[0]):
            parsed = config
        else:
            parsed = jc_parse("etc_group", config)
    else:
        parsed = jc_parse("etc_group", config)

    if not parsed:
        return {}

    entries = parsed

    result: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        name = entry.get("name")
        gid = _to_int(entry.get("gid"))

        if key == "id":
            if gid is None:
                continue
            result[str(gid)] = {"name": name}
        else:
            if name:
                result[name] = {"id": gid}
            elif gid is not None:
                result[str(gid)] = {"id": gid}

    return result


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = ["group_info"]
