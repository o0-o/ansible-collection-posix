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

from typing import Any, Union

from ansible_collections.o0_o.posix.plugins.module_utils.jc_utils import (
    jc_parse,
)

VALID_KEYS = {"id", "name"}

# A group line's fields: name, password, gid, members
GROUP_FIELDS = 4


def _restore_members_field(text: str) -> str:
    """Give back the empty members field a producer left off.

    A group with no members is four fields the last of which is
    empty, and the flat file writes it that way on every platform.
    ``getent group`` on the BSDs does not: FreeBSD and OpenBSD print
    ``daemon:*:1`` where Linux prints ``daemon:x:1:``, dropping the
    delimiter along with the field.  Both mean a group nobody is a
    secondary member of, so the field is restored rather than the
    line being treated as malformed - the alternative is a parser
    that raises on output a real getent really produces, which reads
    to the caller as a host that has no getent.

    A field cannot contain the delimiter, so counting delimiters
    counts fields.  Only a line one field short is padded; anything
    else is passed through for the parser to judge.

    :param str text: Group content as a producer wrote it
    :returns str: The same content, every short line padded
    """
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if (
            stripped
            and not stripped.startswith("#")
            and line.count(":") == GROUP_FIELDS - 2
        ):
            line = f"{line}:"
        lines.append(line)

    return "\n".join(lines)


def group_info(
    config: Union[str, dict[str, Any], list[dict[str, Any]]], key: str = "id"
) -> dict[str, dict[str, Any]]:
    """Normalize /etc/group data into lookup dictionaries."""

    if key not in VALID_KEYS:
        raise ValueError(f"Unsupported key '{key}', expected 'id' or 'name'")

    entries: list[dict[str, Any]]

    if isinstance(config, dict):
        if "stdout" in config or "content" in config:
            parsed = jc_parse(
                "group", config, normalize=_restore_members_field
            )
        elif "gid" in config or "name" in config:
            parsed = [config]
        else:
            return {}
    elif isinstance(config, list):
        if (
            config
            and isinstance(config[0], dict)
            and ("gid" in config[0] or "name" in config[0])
        ):
            parsed = config
        else:
            parsed = jc_parse(
                "group", config, normalize=_restore_members_field
            )
    else:
        parsed = jc_parse("group", config, normalize=_restore_members_field)

    if not parsed:
        return {}

    entries = parsed

    result: dict[str, dict[str, Any]] = {}
    for entry in entries:
        name = entry.get("name")
        if not name:
            name = entry.get("group_name") or entry.get("group")

        gid = _to_int(entry.get("gid"))

        members = entry.get("members")
        if members is None:
            members = entry.get("users")
        members_list = normalize_group_members(members)

        if key == "id":
            if gid is None:
                continue
            result[str(gid)] = {"name": name, "members": members_list}
        else:
            if name:
                result[name] = {"id": gid, "members": members_list}
            elif gid is not None:
                result[str(gid)] = {"id": gid, "members": members_list}

    return result


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_group_members(value: Any) -> list[str]:
    if value in (None, ""):
        return []

    if isinstance(value, str):
        return [
            member.strip() for member in value.split(",") if member.strip()
        ]

    if isinstance(value, (tuple, set)):
        return [str(member) for member in value if member not in (None, "")]

    if isinstance(value, list):
        return [str(member) for member in value if member not in (None, "")]

    return [str(value)]


__all__ = ["group_info", "normalize_group_members"]
