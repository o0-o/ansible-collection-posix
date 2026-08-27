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

from typing import Any, Generator

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

SHELLS = "\n".join(
    [
        "# List of acceptable shells",
        "/bin/sh",
        "/bin/zsh",
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
        if cmd == ["cat", "/etc/shells"]:
            return {"rc": 0, "stdout": SHELLS}
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
        "o0_paths",
        "o0_homes",
        "o0_shell_files",
    }
    assert "users" not in result
    assert "groups" not in result
    assert "homes" not in result
    assert "shells" not in result
    assert "o0_shells" not in result


def test_users_action_files_the_shells_file_at_its_path(plugin) -> None:
    """Test the login shells a host names are the parsed meaning of
    /etc/shells, filed at that path beside the bytes they came from,
    which is where the facts module publishes them too."""
    result = plugin.run(task_vars={})

    assert result["o0_paths"]["/etc/shells"] == {
        "content": SHELLS,
        "config": ["/bin/sh", "/bin/zsh"],
    }


def test_users_action_files_a_named_shells_path(monkeypatch, plugin) -> None:
    """Test the file the option names is the path the parse lands at,
    so a host that keeps its login shells elsewhere is not filed as
    having answered for /etc/shells."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == ["cat", "/etc/passwd"]:
            return {"rc": 0, "stdout": PASSWD}
        if cmd == ["cat", "/etc/group"]:
            return {"rc": 0, "stdout": GROUP}
        if cmd == ["cat", "/usr/local/etc/shells"]:
            return {"rc": 0, "stdout": SHELLS}
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_command", mock_cmd)
    plugin._task.args = {"shells_path": "/usr/local/etc/shells"}

    result = plugin.run(task_vars={})

    assert result["o0_paths"]["/usr/local/etc/shells"]["config"] == [
        "/bin/sh",
        "/bin/zsh",
    ]
    assert "/etc/shells" not in result["o0_paths"]


def test_users_action_without_a_shells_file(monkeypatch, plugin) -> None:
    """Test a host that names no login shells leaves the path
    unmentioned, rather than filed as a file that exists and names
    none."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == ["cat", "/etc/passwd"]:
            return {"rc": 0, "stdout": PASSWD}
        if cmd == ["cat", "/etc/group"]:
            return {"rc": 0, "stdout": GROUP}
        return {"rc": 1, "stderr": "no such file"}

    monkeypatch.setattr(plugin, "_command", mock_cmd)

    result = plugin.run(task_vars={})

    assert "o0_paths" not in result
    assert result["o0_users"]["1000"]["shell"] == "/bin/zsh"


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


READ_TYPES = {
    "/var/root": "directory",
    "/home/o0-o": "directory",
    "/bin/sh": "regular",
    "/bin/zsh": "regular",
}


def _counting_read(monkeypatch, plugin) -> list[list[str]]:
    """Answer the read action with each path's type, counting reads.

    :param monkeypatch: The pytest monkeypatch fixture
    :param plugin: Action instance to patch
    :returns list[list[str]]: The path lists the action asked for
    """
    asked: list[list[str]] = []

    def mock_read(**kwargs: Any) -> dict[str, Any]:
        paths = kwargs["paths"]
        if isinstance(paths, str):
            paths = [paths]
        asked.append(list(paths))
        return {
            "paths": {
                path: {"type": READ_TYPES.get(path, "directory")}
                for path in paths
            }
        }

    monkeypatch.setattr(plugin, "_read", mock_read)
    return asked


def test_users_action_reads_homes_and_shells_in_one_batch(
    monkeypatch, plugin
) -> None:
    """Test one gather spends one metadata read over the deduplicated
    home and shell paths, not one read for each fact."""
    asked = _counting_read(monkeypatch, plugin)

    plugin.run(task_vars={})

    assert asked == [["/bin/sh", "/bin/zsh", "/home/o0-o", "/var/root"]]


def test_users_action_batch_leaves_the_facts_alone(
    monkeypatch, plugin
) -> None:
    """Test the batched read publishes what the per-fact reads did."""
    _counting_read(monkeypatch, plugin)

    result = plugin.run(task_vars={})

    assert result["o0_homes"]["/home/o0-o"] == {
        "type": "directory",
        "tags": ["posix", "home"],
        "residents": [1000],
    }
    assert result["o0_homes"]["/var/root"]["residents"] == [0]
    assert result["o0_shell_files"]["/bin/zsh"] == {
        "type": "regular",
        "tags": ["posix", "shell"],
    }
    assert set(result["o0_shell_files"]) == {"/bin/sh", "/bin/zsh"}
