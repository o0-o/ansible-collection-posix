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

"""Unit tests for user_utils module."""

from __future__ import annotations

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils.user_utils import (
    lookup_group,
    lookup_user,
)


# Sample data matching the structure from o0_o.posix.users module
USERS_BY_ID = {
    "0": {
        "name": "root",
        "gecos": "root",
        "home": "/root",
        "shell": "/bin/sh",
        "group": 0,
        "groups": [0],
    },
    "1000": {
        "name": "o0-o",
        "gecos": "o0-o",
        "home": "/home/o0-o",
        "shell": "/bin/zsh",
        "group": 20,
        "groups": [20, 101],
    },
}

USERS_BY_NAME = {
    "root": {
        "id": 0,
        "gecos": "root",
        "home": "/root",
        "shell": "/bin/sh",
        "group": "root",
        "groups": ["root"],
    },
    "o0-o": {
        "id": 1000,
        "gecos": "o0-o",
        "home": "/home/o0-o",
        "shell": "/bin/zsh",
        "group": "staff",
        "groups": ["staff", "access_bpf"],
    },
}

GROUPS_BY_ID = {
    "0": {"name": "root", "members": [0]},
    "20": {"name": "staff", "members": [1000]},
    "101": {"name": "access_bpf", "members": [1000]},
}

GROUPS_BY_NAME = {
    "root": {"id": 0, "members": [0]},
    "staff": {"id": 20, "members": [1000]},
    "access_bpf": {"id": 101, "members": [1000]},
}


def test_lookup_user_by_uid() -> None:
    """Test looking up user by UID (integer)."""
    result = lookup_user(1000, USERS_BY_ID)
    assert result is not None
    assert result["name"] == "o0-o"
    assert result["home"] == "/home/o0-o"


def test_lookup_user_by_username() -> None:
    """Test looking up user by username (string)."""
    result = lookup_user("o0-o", USERS_BY_NAME)
    assert result is not None
    assert result["id"] == 1000
    assert result["home"] == "/home/o0-o"


def test_lookup_user_uid_not_found() -> None:
    """Test looking up non-existent UID returns None."""
    result = lookup_user(9999, USERS_BY_ID)
    assert result is None


def test_lookup_user_username_not_found() -> None:
    """Test looking up non-existent username returns None."""
    result = lookup_user("nobody", USERS_BY_NAME)
    assert result is None


def test_lookup_user_with_none_users() -> None:
    """Test looking up user when users dict is None."""
    result = lookup_user(1000, None)
    assert result is None


def test_lookup_user_with_invalid_type() -> None:
    """Test looking up user with invalid identifier type."""
    result = lookup_user([], USERS_BY_ID)
    assert result is None


def test_lookup_group_by_gid() -> None:
    """Test looking up group by GID (integer)."""
    result = lookup_group(20, GROUPS_BY_ID)
    assert result is not None
    assert result["name"] == "staff"
    assert result["members"] == [1000]


def test_lookup_group_by_name() -> None:
    """Test looking up group by name (string)."""
    result = lookup_group("staff", GROUPS_BY_NAME)
    assert result is not None
    assert result["id"] == 20
    assert result["members"] == [1000]


def test_lookup_group_gid_not_found() -> None:
    """Test looking up non-existent GID returns None."""
    result = lookup_group(9999, GROUPS_BY_ID)
    assert result is None


def test_lookup_group_name_not_found() -> None:
    """Test looking up non-existent group name returns None."""
    result = lookup_group("nogroup", GROUPS_BY_NAME)
    assert result is None


def test_lookup_group_with_none_groups() -> None:
    """Test looking up group when groups dict is None."""
    result = lookup_group(20, None)
    assert result is None


def test_lookup_group_with_invalid_type() -> None:
    """Test looking up group with invalid identifier type."""
    result = lookup_group([], GROUPS_BY_ID)
    assert result is None


def test_lookup_user_by_uid_includes_id() -> None:
    """Test that looking up by UID always includes 'id' field."""
    result = lookup_user(1000, USERS_BY_ID)
    assert result is not None
    assert "id" in result
    assert result["id"] == 1000


def test_lookup_user_by_name_from_id_dict_includes_id() -> None:
    """Test that looking up by name from ID-keyed dict includes 'id'."""
    result = lookup_user("o0-o", USERS_BY_ID)
    assert result is not None
    assert "id" in result
    assert result["id"] == 1000


def test_lookup_group_by_gid_includes_id() -> None:
    """Test that looking up by GID always includes 'id' field."""
    result = lookup_group(20, GROUPS_BY_ID)
    assert result is not None
    assert "id" in result
    assert result["id"] == 20


def test_lookup_group_by_name_from_id_dict_includes_id() -> None:
    """Test that looking up by name from ID-keyed dict includes 'id'."""
    result = lookup_group("staff", GROUPS_BY_ID)
    assert result is not None
    assert "id" in result
    assert result["id"] == 20
