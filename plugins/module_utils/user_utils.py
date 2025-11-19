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

"""Utilities for looking up users and groups by ID or name."""

from __future__ import annotations

from typing import Any, Optional, Union


def lookup_user(
    identifier: Union[int, str], users: dict[str, dict[str, Any]]
) -> Optional[dict[str, Any]]:
    """Look up user by UID or username.

    Always returns user data with an 'id' field containing the numeric UID.

    :param Union[int, str] identifier: UID (int) or username (str)
    :param dict[str, dict[str, Any]] users: Users dict from o0_o.posix.users
    :returns Optional[dict[str, Any]]: User data with 'id' field, or None
        if not found
    """
    if users is None:
        return None

    if isinstance(identifier, int):
        # Look up by UID - add 'id' field if not present
        user_data = users.get(str(identifier))
        if user_data is not None:
            result = user_data.copy()
            if "id" not in result:
                result["id"] = identifier
            return result
        return None
    elif isinstance(identifier, str):
        # Look up by name - first try as key (for key='name' mode)
        if identifier in users:
            return users[identifier]
        # Otherwise search by 'name' field (for key='id' mode)
        for uid_str, user_data in users.items():
            if user_data.get("name") == identifier:
                result = user_data.copy()
                if "id" not in result:
                    result["id"] = int(uid_str)
                return result
        return None
    else:
        return None


def lookup_group(
    identifier: Union[int, str], groups: dict[str, dict[str, Any]]
) -> Optional[dict[str, Any]]:
    """Look up group by GID or group name.

    Always returns group data with an 'id' field containing the numeric GID.

    :param Union[int, str] identifier: GID (int) or group name (str)
    :param dict[str, dict[str, Any]] groups: Groups dict from
        o0_o.posix.users
    :returns Optional[dict[str, Any]]: Group data with 'id' field, or None
        if not found
    """
    if groups is None:
        return None

    if isinstance(identifier, int):
        # Look up by GID - add 'id' field if not present
        group_data = groups.get(str(identifier))
        if group_data is not None:
            result = group_data.copy()
            if "id" not in result:
                result["id"] = identifier
            return result
        return None
    elif isinstance(identifier, str):
        # Look up by name - first try as key (for key='name' mode)
        if identifier in groups:
            return groups[identifier]
        # Otherwise search by 'name' field (for key='id' mode)
        for gid_str, group_data in groups.items():
            if group_data.get("name") == identifier:
                result = group_data.copy()
                if "id" not in result:
                    result["id"] = int(gid_str)
                return result
        return None
    else:
        return None
