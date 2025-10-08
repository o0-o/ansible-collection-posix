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

from ansible_collections.o0_o.posix.plugins.action.read import ActionModule


@pytest.fixture
def plugin(base) -> Generator[ActionModule, None, None]:
    """Create an ActionModule instance for read action tests."""
    base._task.async_val = False
    base._task.action = "read"
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
    return plugin


def test_read_regular_file(monkeypatch, plugin) -> None:
    """Test gathering metadata and content for a regular file."""

    args_path = "/etc/sample"

    stat_result = {
        "stat": {
            "exists": True,
            "isreg": True,
            "mode": "0644",
            "pw_name": "root",
            "gr_name": "wheel",
            "writeable": True,
            "selinux_label": "system_u:object_r:etc_t:s0",
            "attr_flags": "----i--e--",
            "nlink": 2,
            "inode": 4242,
        }
    }

    slurp_content = "hello world\n"

    command_calls = []

    def mock_run_action(
        name: str, args: Dict[str, object], task_vars=None, check_mode=None
    ):
        if name == "ansible.builtin.stat":
            return stat_result
        raise AssertionError(f"Unexpected action {name}")

    def mock_execute_module(
        module_name: str, module_args: Dict[str, object], task_vars=None
    ):
        if module_name == "o0_o.posix.slurp64":
            return {"content": slurp_content}
        raise AssertionError(f"Unexpected module {module_name}")

    def mock_cmd(cmd, task_vars=None, check_mode=None):
        command_calls.append(cmd)
        if cmd[0] == "df":
            return {
                "rc": 0,
                "stdout": (
                    "Filesystem 512-blocks Used Available Capacity Mounted on\n"
                    "/dev/disk1s1 100 10 90 10% /\n"
                ),
            }
        if cmd[0] == "sh":
            return {
                "rc": 0,
                "stdout": (f"{args_path}\n" f"{args_path}_hard\n"),
            }
        if cmd[0] == "getfacl":
            return {"rc": 0, "stdout": "# file: sample\nuser::rw-"}
        if cmd[0] == "getfattr":
            return {"rc": 0, "stdout": '# file: sample\nuser.comment="note"'}
        if cmd[0] == "lsattr":
            return {"rc": 0, "stdout": "----i--e-- sample\n"}
        if cmd[0] == "file":
            return {"rc": 0, "stdout": "utf-8\n"}
        raise AssertionError(f"Unexpected command {cmd}")

    monkeypatch.setattr(plugin, "_run_action", mock_run_action)
    monkeypatch.setattr(plugin, "_execute_module", mock_execute_module)
    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    plugin._task.args = {
        "path": args_path,
        "content": True,
        "find_hardlinks": True,
    }
    result = plugin.run(task_vars={})

    file_info = result["paths"][args_path]
    assert file_info["type"] == "regular"
    assert file_info["mode"] == "0644"
    assert file_info["owner"] == "root"
    assert file_info["group"] == "wheel"
    assert file_info["writable"] is True
    assert file_info["name"] == "sample"
    assert file_info["parent"] == "/etc"
    assert file_info["selinux"] == "system_u:object_r:etc_t:s0"
    assert file_info["flags"] == ["----i--e--"]
    assert file_info["acl"]["type"] == "posix"
    assert file_info["acl"]["text"].startswith("# file")
    assert "user.comment" in file_info["xattrs"]
    assert file_info["encoding"] == "utf-8"
    assert "hello world" in file_info["content"]
    links = file_info["links"]
    expected_hard = f"{args_path}_hard"
    assert links == [expected_hard]
    assert any(
        cmd[0] == "sh" and "head -n 2" in cmd[2] for cmd in command_calls
    )


def test_read_symlink(monkeypatch, plugin) -> None:
    """Test that symlink returns soft link target without content."""

    stat_result = {
        "stat": {
            "exists": True,
            "islnk": True,
            "lnk_source": "/var/target",
            "mode": "0777",
            "pw_name": "root",
            "gr_name": "wheel",
            "nlink": 1,
            "writable": False,
        }
    }

    def mock_run_action(
        name: str, args: Dict[str, object], task_vars=None, check_mode=None
    ):
        if name == "ansible.builtin.stat":
            return stat_result
        raise AssertionError("slurp should not be called for symlinks")

    def mock_cmd(cmd, task_vars=None, check_mode=None):
        return {"rc": 1, "stdout": ""}

    monkeypatch.setattr(plugin, "_run_action", mock_run_action)
    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    plugin._task.args = {"path": "/var/link", "content": True}
    result = plugin.run(task_vars={})

    file_info = result["paths"]["/var/link"]
    assert file_info["type"] == "link"
    assert file_info["writable"] is False
    links = file_info["links"]
    assert links == ["/var/target"]
    assert "link" not in file_info
    assert "content" not in file_info
    assert "encoding" not in file_info


def test_read_pipe_excludes_links(monkeypatch, plugin) -> None:
    """Pipes omit the links field even when nlink is reported."""

    pipe_path = "/tmp/fifo"

    stat_result = {
        "stat": {
            "exists": True,
            "isfifo": True,
            "mode": "0644",
            "pw_name": "root",
            "gr_name": "wheel",
            "nlink": 1,
        }
    }

    def mock_run_action(
        name: str, args: Dict[str, object], task_vars=None, check_mode=None
    ):
        if name == "ansible.builtin.stat":
            return stat_result
        raise AssertionError(name)

    monkeypatch.setattr(plugin, "_run_action", mock_run_action)

    def mock_cmd(cmd, task_vars=None, check_mode=None):
        return {"rc": 1, "stdout": ""}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    plugin._task.args = {"path": pipe_path}
    result = plugin.run(task_vars={})

    info = result["paths"][pipe_path]
    assert info["type"] == "pipe"
    assert "links" not in info


def test_find_symlinks_adds_entries(monkeypatch, plugin) -> None:
    """Symlink discovery adds additional file entries to the result."""

    target_path = "/data/target"
    symlink_path = "/data/linked"

    def mock_run_action(
        name: str, args: Dict[str, object], task_vars=None, check_mode=None
    ):
        if name != "ansible.builtin.stat":
            raise AssertionError(name)
        path = args["path"]
        follow = args.get("follow", False)
        if path == target_path:
            if follow:
                return {"stat": {"exists": True, "inode": 4242}}
            return {
                "stat": {
                    "exists": True,
                    "isreg": True,
                    "mode": "0644",
                    "pw_name": "root",
                    "gr_name": "wheel",
                    "nlink": 1,
                    "inode": 4242,
                }
            }
        if path == symlink_path:
            if follow:
                return {"stat": {"exists": True, "inode": 4242}}
            return {
                "stat": {
                    "exists": True,
                    "islnk": True,
                    "lnk_source": target_path,
                    "nlink": 1,
                }
            }
        raise AssertionError(path)

    monkeypatch.setattr(plugin, "_run_action", mock_run_action)
    monkeypatch.setattr(plugin, "_cmd", lambda *args, **kwargs: {"rc": 1})
    monkeypatch.setattr(
        plugin,
        "_discover_links",
        lambda **kwargs: ([], [symlink_path]),
    )

    plugin._task.args = {
        "path": target_path,
        "find_symlinks": True,
    }
    result = plugin.run(task_vars={})

    assert target_path in result["paths"]
    assert symlink_path in result["paths"]
    assert result["paths"][symlink_path]["type"] == "link"
    assert result["paths"][symlink_path]["links"] == [target_path]


def test_find_symlinks_for_hardlinks(monkeypatch, plugin) -> None:
    """Symlink discovery includes links for discovered hard link paths."""

    primary_path = "/data/file"
    hard_path = "/data/file_hard"
    symlink_path = "/links/file_symlink"

    stat_map = {
        "/": {"exists": True, "isdir": True, "nlink": 2},
        primary_path: {
            "exists": True,
            "isreg": True,
            "nlink": 2,
            "inode": 9001,
        },
        hard_path: {
            "exists": True,
            "isreg": True,
            "nlink": 2,
            "inode": 9001,
        },
        symlink_path: {
            "exists": True,
            "islnk": True,
            "lnk_source": hard_path,
            "nlink": 1,
        },
    }

    def mock_run_action(
        name: str, args: Dict[str, object], task_vars=None, check_mode=None
    ):
        if name != "ansible.builtin.stat":
            raise AssertionError(name)
        path = args["path"]
        follow = args.get("follow", False)
        if follow:
            return {"stat": {"exists": True, "inode": 9001}}
        return {"stat": stat_map[path]}

    def mock_discover(
        path: str,
        task_vars=None,
        inode=None,
        file_type=None,
        expected_total=None,
        include_hardlinks=False,
        include_symlinks=False,
    ):
        if path == primary_path:
            return ([hard_path], [])
        if path == hard_path and include_symlinks:
            return ([], [symlink_path])
        return ([], [])

    monkeypatch.setattr(plugin, "_run_action", mock_run_action)
    monkeypatch.setattr(plugin, "_discover_links", mock_discover)
    monkeypatch.setattr(plugin, "_cmd", lambda *args, **kwargs: {"rc": 1})

    plugin._task.args = {
        "path": primary_path,
        "find_hardlinks": True,
        "find_symlinks": True,
    }
    result = plugin.run(task_vars={})

    assert hard_path in result["paths"]
    assert symlink_path in result["paths"]
    assert result["paths"][hard_path]["type"] == "regular"
    assert result["paths"][symlink_path]["type"] == "link"
    assert result["paths"][symlink_path]["links"] == [hard_path]
    assert result["paths"][primary_path]["links"] == [hard_path]


def test_parents_includes_parent_directories(monkeypatch, plugin) -> None:
    """Parents mode includes parent directories in the result map."""

    path_chain = ["/foo", "/foo/bar", "/foo/bar/baz"]

    stat_map = {
        "/": {"exists": True, "isdir": True, "nlink": 2},
        "/foo": {"exists": True, "isdir": True, "nlink": 2},
        "/foo/bar": {"exists": True, "isdir": True, "nlink": 2},
        "/foo/bar/baz": {"exists": True, "isreg": True, "nlink": 1},
    }

    def mock_run_action(
        name: str, args: Dict[str, object], task_vars=None, check_mode=None
    ):
        if name == "ansible.builtin.stat":
            path = args["path"]
            return {"stat": stat_map[path]}
        raise AssertionError(name)

    monkeypatch.setattr(plugin, "_run_action", mock_run_action)
    monkeypatch.setattr(plugin, "_discover_links", lambda **kwargs: ([], []))
    monkeypatch.setattr(
        plugin, "_cmd", lambda *args, **kwargs: {"rc": 1, "stdout": ""}
    )

    plugin._task.args = {"path": "/foo/bar/baz", "parents": True}
    result = plugin.run(task_vars={})

    assert result["paths"]["/foo"]["type"] == "directory"
    assert result["paths"]["/foo/bar"]["type"] == "directory"
    assert result["paths"]["/foo/bar/baz"]["type"] == "regular"
    assert "/" in result["paths"]
    root_info = result["paths"]["/"]
    assert root_info["name"] == "/"
    assert "parent" not in root_info


def test_directory_content_listing(monkeypatch, plugin) -> None:
    """Directories include a content listing."""

    dir_path = "/opt/data"
    entries = ["/opt/data/a", "/opt/data/b"]

    def mock_run_action(
        name: str, args: Dict[str, object], task_vars=None, check_mode=None
    ):
        if name == "ansible.builtin.stat":
            return {
                "stat": {
                    "exists": True,
                    "isdir": True,
                    "nlink": 2,
                }
            }
        raise AssertionError(name)

    def mock_cmd(cmd, task_vars=None, check_mode=None):
        if cmd and cmd[0] == "find":
            return {"rc": 0, "stdout": "\n".join(entries)}
        return {"rc": 1, "stdout": ""}

    monkeypatch.setattr(plugin, "_run_action", mock_run_action)
    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    plugin._task.args = {"path": dir_path, "content": True}
    result = plugin.run(task_vars={})

    info = result["paths"][dir_path]
    assert info["type"] == "directory"
    assert info["name"] == "data"
    assert info["parent"] == "/opt"
    assert info["content"] == sorted(entries)


def test_parents_limit(monkeypatch, plugin) -> None:
    """Parents option can limit how many directories are included."""

    stat_map = {
        "/": {"exists": True, "isdir": True, "nlink": 2},
        "/foo": {"exists": True, "isdir": True, "nlink": 2},
        "/foo/bar": {"exists": True, "isdir": True, "nlink": 2},
        "/foo/bar/baz": {"exists": True, "isreg": True, "nlink": 1},
    }

    def mock_run_action(
        name: str, args: Dict[str, object], task_vars=None, check_mode=None
    ):
        if name == "ansible.builtin.stat":
            path = args["path"]
            return {"stat": stat_map[path]}
        raise AssertionError(name)

    monkeypatch.setattr(plugin, "_run_action", mock_run_action)
    monkeypatch.setattr(plugin, "_discover_links", lambda **kwargs: ([], []))
    monkeypatch.setattr(
        plugin, "_cmd", lambda *args, **kwargs: {"rc": 1, "stdout": ""}
    )

    plugin._task.args = {"path": "/foo/bar/baz", "parents": 1}
    result = plugin.run(task_vars={})

    assert "/foo/bar" in result["paths"]
    assert "/foo" not in result["paths"]
    assert "/" not in result["paths"]


def test_read_missing_path(monkeypatch, plugin) -> None:
    """Test that missing path returns None instead of raising."""

    def mock_run_action(
        name: str, args: Dict[str, object], task_vars=None, check_mode=None
    ):
        if name == "ansible.builtin.stat":
            return {"stat": {"exists": False}}
        raise AssertionError

    monkeypatch.setattr(plugin, "_run_action", mock_run_action)

    plugin._task.args = {"path": "/missing"}
    result = plugin.run(task_vars={})
    assert result["paths"]["/missing"] is None


def test_read_parents_symlink(monkeypatch, plugin) -> None:
    """Test that parents option expands linked targets."""

    symlink_path = "/var/link"
    target_path = "/var/target"

    stat_map = {
        "/": {"exists": True, "isdir": True, "nlink": 2},
        "/var": {"exists": True, "isdir": True, "nlink": 2},
        symlink_path: {
            "exists": True,
            "islnk": True,
            "lnk_source": target_path,
            "pw_name": "root",
            "gr_name": "wheel",
            "nlink": 1,
        },
        target_path: {
            "exists": True,
            "isreg": True,
            "mode": "0600",
            "pw_name": "root",
            "gr_name": "wheel",
            "nlink": 1,
        },
    }

    def mock_run_action(
        name: str, args: Dict[str, object], task_vars=None, check_mode=None
    ):
        if name == "ansible.builtin.stat":
            path = args["path"]
            return {"stat": stat_map[path]}
        raise AssertionError(f"Unexpected action {name}")

    def mock_execute_module(
        module_name: str, module_args: Dict[str, object], task_vars=None
    ):
        if module_name == "o0_o.posix.slurp64":
            return {"content": "target data"}
        raise AssertionError(f"Unexpected module {module_name}")

    def mock_cmd(cmd, task_vars=None, check_mode=None):
        if cmd[0] == "sh":
            return {"rc": 1, "stdout": ""}
        if cmd[0] == "file":
            return {"rc": 0, "stdout": "utf-8\n"}
        return {"rc": 1, "stdout": ""}

    monkeypatch.setattr(plugin, "_run_action", mock_run_action)
    monkeypatch.setattr(plugin, "_execute_module", mock_execute_module)
    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    plugin._task.args = {
        "path": symlink_path,
        "content": True,
        "parents": True,
    }
    result = plugin.run(task_vars={})

    file_info = result["paths"][symlink_path]
    assert file_info["type"] == "link"
    links = file_info["links"]
    assert links == [target_path]
    assert "link" not in file_info
    target_info = result["paths"][target_path]
    assert target_info["type"] == "regular"
    assert target_info["owner"] == "root"
    assert "target data" in target_info["content"]
    assert "/" in result["paths"]
    root_info = result["paths"]["/"]
    assert root_info["name"] == "/"
    assert "parent" not in root_info


def test_read_parents_hard_links(monkeypatch, plugin) -> None:
    """Parents option expands hard link metadata."""

    primary_path = "/etc/sample"
    hard_path = "/etc/sample_hard"

    stat_map = {
        "/": {"exists": True, "isdir": True, "nlink": 2},
        "/etc": {"exists": True, "isdir": True, "nlink": 2},
        primary_path: {
            "exists": True,
            "isreg": True,
            "mode": "0600",
            "pw_name": "root",
            "gr_name": "wheel",
            "nlink": 2,
            "inode": 9001,
        },
        hard_path: {
            "exists": True,
            "isreg": True,
            "mode": "0600",
            "pw_name": "root",
            "gr_name": "wheel",
            "nlink": 2,
            "inode": 9001,
        },
    }

    command_calls = []

    def mock_run_action(
        name: str, args: Dict[str, object], task_vars=None, check_mode=None
    ):
        if name == "ansible.builtin.stat":
            path = args["path"]
            return {"stat": stat_map[path]}
        raise AssertionError(f"Unexpected action {name}")

    def mock_cmd(cmd, task_vars=None, check_mode=None):
        if cmd[0] == "df":
            return {
                "rc": 0,
                "stdout": (
                    "Filesystem 512-blocks Used Available Capacity Mounted on\n"
                    "/dev/disk1s1 100 10 90 10% /\n"
                ),
            }
        if cmd[0] == "sh":
            command_calls.append(cmd)
            return {
                "rc": 0,
                "stdout": (f"{primary_path}\n" f"{hard_path}\n"),
            }
        return {"rc": 1, "stdout": ""}

    monkeypatch.setattr(plugin, "_run_action", mock_run_action)
    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    plugin._task.args = {
        "path": primary_path,
        "parents": True,
        "find_hardlinks": True,
    }
    result = plugin.run(task_vars={})

    file_info = result["paths"][primary_path]
    assert file_info["type"] == "regular"
    links = file_info["links"]
    assert links == [hard_path]
    hard_info = result["paths"][hard_path]
    assert hard_info["type"] == "regular"
    assert any(
        cmd[0] == "sh" and "head -n 2" in cmd[2] for cmd in command_calls
    )


def test_read_xattr_fallback(monkeypatch, plugin) -> None:
    """Fallback to xattr command when getfattr is unavailable."""

    stat_result = {"stat": {"exists": True, "isreg": True, "nlink": 1}}

    command_calls = []

    def mock_run_action(
        name: str, args: Dict[str, object], task_vars=None, check_mode=None
    ):
        if name == "ansible.builtin.stat":
            return stat_result
        raise AssertionError(name)

    def mock_cmd(cmd, task_vars=None, check_mode=None):
        command_calls.append(cmd)
        if cmd[0] == "getfattr":
            return {"rc": 1, "stdout": ""}
        if cmd[0] == "xattr":
            return {"rc": 0, "stdout": "user.comment: note"}
        if cmd[0] == "sh":
            return {"rc": 1, "stdout": ""}
        return {"rc": 1, "stdout": ""}

    monkeypatch.setattr(plugin, "_run_action", mock_run_action)
    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    plugin._task.args = {"path": "/tmp/file"}
    result = plugin.run(task_vars={})

    info = result["paths"]["/tmp/file"]
    assert info["xattrs"] == ["user.comment"]
    assert any(cmd[0] == "xattr" for cmd in command_calls)


def test_read_flags_fallback(monkeypatch, plugin) -> None:
    """Fallback to ls -ldO when lsattr is unavailable."""

    stat_result = {"stat": {"exists": True, "isreg": True, "nlink": 1}}

    def mock_run_action(
        name: str, args: Dict[str, object], task_vars=None, check_mode=None
    ):
        if name == "ansible.builtin.stat":
            return stat_result
        raise AssertionError(name)

    def mock_cmd(cmd, task_vars=None, check_mode=None):
        if cmd[0] == "lsattr":
            return {"rc": 1, "stdout": ""}
        if cmd[0] == "ls" and "-ldO" in cmd:
            return {
                "rc": 0,
                "stdout": (
                    "-rw-r--r-- 1 user staff uchg 0 Jan 1 00:00 /tmp/file\n"
                ),
            }
        if cmd[0] == "sh":
            return {"rc": 1, "stdout": ""}
        return {"rc": 1, "stdout": ""}

    monkeypatch.setattr(plugin, "_run_action", mock_run_action)
    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    plugin._task.args = {"path": "/tmp/file"}
    result = plugin.run(task_vars={})

    info = result["paths"]["/tmp/file"]
    assert info["flags"] == ["uchg"]


def test_read_multiple_paths(monkeypatch, plugin) -> None:
    """Multiple paths are processed when 'paths' is provided."""

    stat_map = {
        "/tmp/a": {"exists": True, "isreg": True, "nlink": 1},
        "/tmp/b": {"exists": True, "isdir": True, "nlink": 1},
    }

    def mock_run_action(
        name: str, args: Dict[str, object], task_vars=None, check_mode=None
    ):
        if name == "ansible.builtin.stat":
            return {"stat": stat_map[args["path"]]}
        raise AssertionError(name)

    def mock_cmd(cmd, task_vars=None, check_mode=None):
        return {"rc": 1, "stdout": ""}

    monkeypatch.setattr(plugin, "_run_action", mock_run_action)
    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    plugin._task.args = {"paths": ["/tmp/a", "/tmp/b"]}
    result = plugin.run(task_vars={})

    assert result["paths"]["/tmp/a"]["type"] == "regular"
    assert result["paths"]["/tmp/b"]["type"] == "directory"


def base64_bytes(data: bytes) -> str:
    """Helper returning base64 text for fixture content."""
    import base64

    return base64.b64encode(data).decode("ascii")
