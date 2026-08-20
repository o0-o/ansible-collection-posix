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

from typing import Generator

import pytest

from ansible.errors import AnsibleActionFail
from ansible_collections.o0_o.posix.plugins.action.users import ActionModule

PASSWD = "\n".join(
    [
        "root:*:0:0:System Administrator:/var/root:/bin/sh",
        "o0-o:*:1000:20:o0-o:/home/o0-o:/bin/zsh",
    ]
)

GROUP = "\n".join(
    [
        "wheel:*:0:root",
        "staff:*:20:",
        "access_bpf:*:101:o0-o",
    ]
)


@pytest.fixture
def plugin(monkeypatch, base) -> Generator[ActionModule, None, None]:
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
    plugin.inventory_hostname = "localhost"

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == ["cat", "/etc/passwd"]:
            return {"rc": 0, "stdout": PASSWD}
        if cmd == ["cat", "/etc/group"]:
            return {"rc": 0, "stdout": GROUP}
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_command", mock_cmd)
    # Home and shell metadata come from the read action plugin, which
    # is exercised by its own tests.
    monkeypatch.setattr(plugin, "_read", lambda **kwargs: {"paths": {}})
    yield plugin


def test_users_action_returns_canonical_fact_names(plugin) -> None:
    """Test the returns are named for the facts they define."""
    result = plugin.run(task_vars={})

    assert set(result) >= {
        "o0_users",
        "o0_groups",
        "o0_homes",
        "o0_shell_files",
    }
    assert "users" not in result
    assert "groups" not in result
    assert "homes" not in result
    assert "shells" not in result


def test_users_action_composes_canonical_users(plugin) -> None:
    """Test users are keyed by UID and carry the canonical fields."""
    result = plugin.run(task_vars={})

    assert set(result["o0_users"]["1000"]) == {
        "name",
        "uid",
        "gid",
        "gecos",
        "home",
        "shell",
        "groups",
    }
    assert result["o0_users"]["1000"]["name"] == "o0-o"
    assert result["o0_users"]["1000"]["uid"] == 1000
    assert result["o0_users"]["1000"]["gid"] == 20
    assert sorted(result["o0_users"]["1000"]["groups"]) == [20, 101]


def test_users_action_composes_canonical_groups(plugin) -> None:
    """Test groups are keyed by GID and count members as UIDs."""
    result = plugin.run(task_vars={})

    assert set(result["o0_groups"]["20"]) == {"name", "gid", "members"}
    assert result["o0_groups"]["20"]["name"] == "staff"
    assert result["o0_groups"]["20"]["gid"] == 20
    assert result["o0_groups"]["20"]["members"] == [1000]
    assert result["o0_groups"]["0"]["members"] == [0]
    assert result["o0_groups"]["101"]["members"] == [1000]


def test_users_action_rejects_key_option(plugin) -> None:
    """Test the retired key option is no longer accepted."""
    plugin._task.args = {"key": "name"}

    with pytest.raises(AnsibleActionFail):
        plugin.run(task_vars={})


def test_users_action_homes_resident_uids(monkeypatch, plugin) -> None:
    """Test home residents are recorded as UIDs."""
    monkeypatch.setattr(
        plugin,
        "_read",
        lambda **kwargs: {
            "paths": {
                path: {"type": "directory"}
                for path in (
                    kwargs["paths"]
                    if isinstance(kwargs["paths"], list)
                    else [kwargs["paths"]]
                )
            }
        },
    )

    result = plugin.run(task_vars={})

    assert result["o0_homes"]["/home/o0-o"]["residents"] == [1000]
    assert result["o0_homes"]["/var/root"]["residents"] == [0]


def test_users_action_shell_files_extend_prior_gather(
    monkeypatch, plugin
) -> None:
    """Test previously gathered shell file metadata is preserved."""
    monkeypatch.setattr(
        plugin,
        "_read",
        lambda **kwargs: {
            "paths": {
                path: {"type": "file"}
                for path in (
                    kwargs["paths"]
                    if isinstance(kwargs["paths"], list)
                    else [kwargs["paths"]]
                )
            }
        },
    )

    result = plugin.run(
        task_vars={"o0_shell_files": {"/bin/ksh": {"type": "file"}}}
    )

    assert "/bin/ksh" in result["o0_shell_files"]
    assert result["o0_shell_files"]["/bin/zsh"]["tags"] == ["posix", "shell"]
