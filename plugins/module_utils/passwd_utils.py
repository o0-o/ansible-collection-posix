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

"""Utilities for parsing ``/etc/passwd`` content."""

from __future__ import annotations

from typing import Any, Union

from ansible_collections.o0_o.posix.plugins.module_utils.jc_utils import (
    jc_parse,
)

VALID_KEYS = {"id", "name"}


def passwd_info(
    config: Union[str, dict[str, Any], list[dict[str, Any]]],
    key: str = "id",
) -> dict[str, dict[str, Any]]:
    """Normalize ``/etc/passwd`` data into lookup dictionaries."""

    if key not in VALID_KEYS:
        raise ValueError(f"Unsupported key '{key}', expected 'id' or 'name'")

    if isinstance(config, dict):
        if "stdout" in config or "content" in config:
            entries = jc_parse("passwd", config)
        elif "uid" in config or "name" in config:
            entries = [config]
        else:
            return {}
    elif isinstance(config, list):
        if (
            config
            and isinstance(config[0], dict)
            and ("uid" in config[0] or "name" in config[0])
        ):
            entries = config
        else:
            entries = jc_parse("passwd", config)
    else:
        entries = jc_parse("passwd", config)

    if not entries:
        return {}

    result: dict[str, dict[str, Any]] = {}
    for entry in entries:
        name = entry.get("name")
        if not name:
            name = entry.get("username") or entry.get("user")

        uid = _to_int(entry.get("uid"))
        gid = _to_int(entry.get("gid"))
        home = entry.get("home")
        shell = entry.get("shell")

        gecos = entry.get("gecos")
        if not gecos:
            gecos = entry.get("comment")

        payload = {
            "gid": gid,
            "gecos": gecos,
            "home": home,
            "shell": shell,
        }

        if key == "id":
            if uid is None:
                continue
            uid_key = str(uid)
            if uid_key in result:
                # A second line for a uid names the same account again
                # - FreeBSD ships toor beside root - so the first name
                # stands as the name and the rest are its aliases, in
                # file order, rather than the last line overwriting
                # everything the first one said
                known = result[uid_key]
                if name and name != known.get("name"):
                    aliases = known.setdefault("aliases", [])
                    if name not in aliases:
                        aliases.append(name)
                continue
            info = dict(payload)
            info["name"] = name
            result[uid_key] = info
        else:
            if name:
                info = dict(payload)
                info["id"] = uid
                result[name] = info
            elif uid is not None:
                info = dict(payload)
                info["id"] = uid
                result[str(uid)] = info

    return result


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = ["passwd_info"]
