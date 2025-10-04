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

from __future__ import annotations

from typing import Dict, Generator

import pytest

from ansible_collections.o0_o.posix.plugins.action.users import ActionModule


PASSWD_ID = {
    "0": {
        "name": "root",
        "gid": 0,
        "gecos": "root",
        "home": "/root",
        "shell": "/bin/sh",
    },
    "1000": {
        "name": "o0-o",
        "gid": 20,
        "gecos": "o0-o",
        "home": "/home/o0-o",
        "shell": "/bin/zsh",
    },
}

PASSWD_NAME = {
    "root": {
        "id": 0,
        "gid": 0,
        "gecos": "root",
        "home": "/root",
        "shell": "/bin/sh",
    },
    "o0-o": {
        "id": 1000,
        "gid": 20,
        "gecos": "o0-o",
        "home": "/home/o0-o",
        "shell": "/bin/zsh",
    },
}

GROUP_ID = {
    "0": {"name": "root", "members": []},
    "20": {"name": "staff", "members": []},
    "101": {"name": "access_bpf", "members": []},
}

GROUP_NAME = {
    "root": {"id": 0, "members": []},
    "staff": {"id": 20, "members": []},
    "access_bpf": {"id": 101, "members": []},
}

GROUP_ENTRIES = [
    {"group_name": "root", "gid": 0, "members": ""},
    {"group_name": "staff", "gid": 20, "members": "", "users": ""},
    {"group_name": "access_bpf", "gid": 101, "members": "o0-o"},
]


@pytest.fixture
def plugin(base) -> Generator[ActionModule, None, None]:
    base._task.async_val = False
    base._task.action = "users"
    base._task.args = {}

    plugin = ActionModule(
        task=base._task,
        connection=base._connection,
        play_context=base._play_context,
        loader=base._loader,
        templar=base._templar,
        shared_loader_obj=base._shared_loader_obj,
    )
    plugin._display = base._display
    yield plugin


def test_users_action_by_id(
    monkeypatch: pytest.MonkeyPatch, plugin: ActionModule
) -> None:
    """Users keyed by id include primary and supplementary groups."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == ["cat", "/etc/passwd"]:
            return {"rc": 0, "stdout": "PASSWD"}
        if cmd == ["cat", "/etc/group"]:
            return {"rc": 0, "stdout": "GROUP"}
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)
    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.action.users.passwd_info",
        lambda content, key="id": PASSWD_ID if key == "id" else PASSWD_NAME,
    )
    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.action.users.group_info",
        lambda content, key="id": GROUP_ID if key == "id" else GROUP_NAME,
    )
    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.action.users.jc_parse",
        lambda parser, data: GROUP_ENTRIES,
    )

    result = plugin.run(task_vars={})

    assert result["users"]["1000"]["group"] == 20
    assert sorted(result["users"]["1000"]["groups"]) == [20, 101]
    assert result["groups"]["0"]["members"] == ["root"]
    assert result["groups"]["20"]["name"] == "staff"
    assert result["groups"]["20"]["members"] == ["o0-o"]


def test_users_action_by_name(
    monkeypatch: pytest.MonkeyPatch, plugin: ActionModule
) -> None:
    """Users keyed by name expose textual groups."""

    plugin._task.args = {"key": "name"}

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == ["cat", "/etc/passwd"]:
            return {"rc": 0, "stdout": "PASSWD"}
        if cmd == ["cat", "/etc/group"]:
            return {"rc": 0, "stdout": "GROUP"}
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)
    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.action.users.passwd_info",
        lambda content, key="id": PASSWD_ID if key == "id" else PASSWD_NAME,
    )
    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.action.users.group_info",
        lambda content, key="id": GROUP_ID if key == "id" else GROUP_NAME,
    )
    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.action.users.jc_parse",
        lambda parser, data: GROUP_ENTRIES,
    )

    result = plugin.run(task_vars={})

    user_entry = result["users"]["o0-o"]
    assert user_entry["group"] == "staff"
    assert sorted(user_entry["groups"]) == ["access_bpf", "staff"]
    assert result["groups"]["root"]["members"] == ["root"]
    assert result["groups"]["staff"]["id"] == 20
    assert result["groups"]["staff"]["members"] == ["o0-o"]
