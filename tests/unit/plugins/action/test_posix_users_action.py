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

from typing import Any, Generator, Optional

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

FILES = {
    "/etc/passwd": PASSWD,
    "/etc/group": GROUP,
    "/etc/shells": SHELLS,
}


def _mock_run(
    monkeypatch,
    plugin: ActionModule,
    files: dict[str, Optional[str]],
    getent: Optional[dict[str, str]] = None,
) -> list[list[dict[str, Any]]]:
    """Answer the module's one batch of file reads and probes.

    The module reads every file it needs in a single batch and asks
    the host for its own resolved view of the users in the same one,
    so the mock answers a list of requests rather than one command at
    a time. A path mapped to None answers as a file that is not
    there, and a host given no ``getent`` answers as one that has no
    getent at all - which is the macOS case, and the default here.

    :param monkeypatch: The pytest monkeypatch fixture
    :param ActionModule plugin: Action instance to patch
    :param dict[str, Optional[str]] files: Content per path
    :param Optional[dict[str, str]] getent: Enumeration per database,
        or None for a host with no getent
    :returns list[list[dict[str, Any]]]: The batches the module issued
    """
    batches: list[list[dict[str, Any]]] = []

    def mock_run(commands, **kwargs) -> list[dict[str, Any]]:
        batches.append(commands)
        answered = []
        for request in commands:
            if request["type"].startswith("getent_"):
                database = request["type"].split("_", 1)[1]
                output = (getent or {}).get(database)
                if output is None:
                    answered.append(
                        {
                            **request,
                            "rc": 127,
                            "stdout": "",
                            "stderr": "sh: getent: not found",
                        }
                    )
                else:
                    answered.append(
                        {**request, "rc": 0, "stdout": output, "stderr": ""}
                    )
                continue

            content = files.get(request["args"]["path"])
            if content is None:
                answered.append(
                    {**request, "rc": 1, "stdout": "", "stderr": "no file"}
                )
            else:
                answered.append(
                    {**request, "rc": 0, "stdout": content, "stderr": ""}
                )
        return answered

    monkeypatch.setattr(plugin, "_run", mock_run)
    return batches


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

    _mock_run(monkeypatch, plugin, FILES)
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
        "o0_shell_files",
        "o0_shells",
    }
    assert "users" not in result
    assert "groups" not in result
    assert "homes" not in result
    assert "shells" not in result
    # The login shells the host names, keyed by path so that
    # user.shell in o0_shells is a question a host can answer. This
    # module names them and runs none, so every key is empty.
    assert set(result["o0_shells"]) == set(
        result["o0_paths"]["/etc/shells"]["config"]
    )
    assert all(rows == {} for rows in result["o0_shells"].values())
    # A home is a path, so it is an entry of the path store rather
    # than a fact of its own
    assert "o0_homes" not in result


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

    _mock_run(
        monkeypatch,
        plugin,
        {
            "/etc/passwd": PASSWD,
            "/etc/group": GROUP,
            "/usr/local/etc/shells": SHELLS,
        },
    )
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

    _mock_run(
        monkeypatch,
        plugin,
        {"/etc/passwd": PASSWD, "/etc/group": GROUP, "/etc/shells": None},
    )

    result = plugin.run(task_vars={})

    assert "o0_paths" not in result
    assert result["o0_users"]["1000"]["shell"] == "/bin/zsh"


def test_users_action_reads_its_files_in_one_batch(
    monkeypatch, plugin
) -> None:
    """Test the three files and both probes ride one round trip. The
    module spent one cat apiece, which is three round trips for facts
    a single batch answers, and the same three the facts module
    already batched. getent joins them for free: it is a command like
    any other, and the batch was already being spent."""
    batches = _mock_run(monkeypatch, plugin, FILES)

    plugin.run(task_vars={})

    assert len(batches) == 1
    assert [request["command"] for request in batches[0]] == [
        ("cat", "/etc/passwd"),
        ("cat", "/etc/group"),
        ("cat", "/etc/shells"),
        ("getent", "passwd"),
        ("getent", "group"),
    ]


def test_users_action_fails_on_an_unreadable_passwd(
    monkeypatch, plugin
) -> None:
    """Test a file the composition cannot do without fails the task,
    naming the path and what the host said about it, rather than
    publishing a shape composed from half a host."""
    _mock_run(
        monkeypatch,
        plugin,
        {"/etc/passwd": None, "/etc/group": GROUP, "/etc/shells": SHELLS},
    )

    with pytest.raises(AnsibleActionFail, match="/etc/passwd"):
        plugin.run(task_vars={})


def test_users_action_gathers_no_ssh_keys(monkeypatch, plugin) -> None:
    """Test no entry carries keys. Reading them cost four to six round
    trips per user, and what an SSH key means is the ssh collection's
    to say, so the gather leaves both to it."""
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

    assert all("keys" not in user for user in result["o0_users"].values())


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
        "sources",
    }
    assert result["o0_users"]["1000"]["name"] == "o0-o"
    assert result["o0_users"]["1000"]["uid"] == 1000
    assert result["o0_users"]["1000"]["gid"] == 20
    assert sorted(result["o0_users"]["1000"]["groups"]) == [20, 101]


def test_users_action_composes_canonical_groups(plugin) -> None:
    """Test groups are keyed by GID and count members as UIDs."""
    result = plugin.run(task_vars={})

    assert set(result["o0_groups"]["20"]) == {
        "name",
        "gid",
        "members",
        "sources",
    }
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
    """Test home residents are recorded as UIDs, at the home's own key
    in the path store."""
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

    assert result["o0_paths"]["/home/o0-o"]["residents"] == [1000]
    assert result["o0_paths"]["/var/root"]["residents"] == [0]
    # The homes and the shells file accumulate in the one store
    # rather than either replacing the other
    assert result["o0_paths"]["/etc/shells"]["config"] == [
        "/bin/sh",
        "/bin/zsh",
    ]


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

    assert result["o0_paths"]["/home/o0-o"] == {
        "type": "directory",
        "tags": ["posix", "home"],
        "residents": [1000],
    }
    assert result["o0_paths"]["/var/root"]["residents"] == [0]
    assert result["o0_shell_files"]["/bin/zsh"] == {
        "type": "regular",
        "tags": ["posix", "shell"],
    }
    assert set(result["o0_shell_files"]) == {"/bin/sh", "/bin/zsh"}
