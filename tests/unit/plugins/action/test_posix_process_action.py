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

from ansible.errors import AnsibleConnectionFailure
from ansible_collections.o0_o.posix.plugins.action.process import ActionModule


@pytest.fixture
def plugin(base) -> Generator[ActionModule, None, None]:
    """Create an ActionModule instance for process tests."""

    base._task.async_val = False
    base._task.action = "process"
    base._task.args = {}
    base._task.check_mode = False

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


def test_process_all_processes(monkeypatch, plugin) -> None:
    """Test getting all processes when no filters specified."""

    def mock_cmd(command, task_vars=None):
        return {"rc": 0, "stdout": "", "stderr": ""}

    def mock_jc_parse(parser, data, quiet=True, raw=False):
        return [
            {"pid": 1, "command": "/sbin/init"},
            {"pid": 100, "command": "/usr/sbin/sshd -D"},
        ]

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)
    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.action.process.jc_parse",
        mock_jc_parse,
    )

    plugin._task.args = {}
    result = plugin.run(task_vars={})

    assert result["changed"] is False
    assert len(result["processes"]) == 2
    assert result["processes"][0]["pid"] == 1
    assert result["processes"][1]["pid"] == 100


def test_process_filter_by_pid(monkeypatch, plugin) -> None:
    """Test filtering processes by PID."""

    def mock_cmd(command, task_vars=None):
        return {"rc": 0, "stdout": "", "stderr": ""}

    def mock_jc_parse(parser, data, quiet=True, raw=False):
        return [
            {"pid": 1, "command": "/sbin/init"},
            {"pid": 100, "command": "/usr/sbin/sshd -D"},
            {"pid": 200, "command": "/usr/sbin/httpd"},
        ]

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)
    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.action.process.jc_parse",
        mock_jc_parse,
    )

    plugin._task.args = {"pids": [100]}
    result = plugin.run(task_vars={})

    assert len(result["processes"]) == 1
    assert result["processes"][0]["pid"] == 100


def test_process_filter_by_executable(monkeypatch, plugin) -> None:
    """Test filtering processes by executable name."""

    def mock_cmd(command, task_vars=None):
        return {"rc": 0, "stdout": "", "stderr": ""}

    def mock_jc_parse(parser, data, quiet=True, raw=False):
        return [
            {"pid": 1, "command": "/sbin/init"},
            {"pid": 100, "command": "/usr/sbin/sshd -D"},
            {"pid": 200, "command": "/usr/sbin/httpd"},
        ]

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)
    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.action.process.jc_parse",
        mock_jc_parse,
    )

    plugin._task.args = {"executables": ["sshd"]}
    result = plugin.run(task_vars={})

    assert len(result["processes"]) == 1
    assert result["processes"][0]["pid"] == 100
    assert "sshd" in result["processes"][0]["command"]


def test_process_filter_basename_match(monkeypatch, plugin) -> None:
    """Test filtering matches basename when full path provided."""

    def mock_cmd(command, task_vars=None):
        return {"rc": 0, "stdout": "", "stderr": ""}

    def mock_jc_parse(parser, data, quiet=True, raw=False):
        return [
            {"pid": 100, "command": "/usr/sbin/sshd -D"},
            {
                "pid": 200,
                "command": "/usr/local/sbin/sshd -f /etc/ssh/custom.conf",
            },
        ]

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)
    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.action.process.jc_parse",
        mock_jc_parse,
    )

    plugin._task.args = {"executable": "sshd"}
    result = plugin.run(task_vars={})

    assert len(result["processes"]) == 2
    assert result["processes"][0]["pid"] == 100
    assert result["processes"][1]["pid"] == 200


def test_process_combined_filters(monkeypatch, plugin) -> None:
    """Test combining PID and executable filters."""

    def mock_cmd(command, task_vars=None):
        return {"rc": 0, "stdout": "", "stderr": ""}

    def mock_jc_parse(parser, data, quiet=True, raw=False):
        return [
            {"pid": 100, "command": "/usr/sbin/sshd -D"},
            {"pid": 200, "command": "/usr/sbin/httpd"},
            {"pid": 300, "command": "/usr/sbin/sshd -p 2222"},
        ]

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)
    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.action.process.jc_parse",
        mock_jc_parse,
    )

    plugin._task.args = {"pids": [200], "executables": ["sshd"]}
    result = plugin.run(task_vars={})

    # Should match PID 200 (httpd) AND both sshd processes
    assert len(result["processes"]) == 3


def test_process_check_mode(monkeypatch, plugin) -> None:
    """Test check mode returns empty processes list."""

    plugin._task.check_mode = True
    plugin._task.args = {}
    result = plugin.run(task_vars={})

    assert result["processes"] == []
    assert "changed" not in result or result["changed"] is False


def test_process_ps_command_failure(monkeypatch, plugin) -> None:
    """Test handling of ps command failure."""

    def mock_cmd(command, task_vars=None):
        return {"rc": 1, "stdout": "", "stderr": "ps: command not found"}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    plugin._task.args = {}
    result = plugin.run(task_vars={})

    assert result["failed"] is True
    assert "ps command failed" in result["msg"]
    assert result["processes"] == []


def test_process_jc_parse_failure(monkeypatch, plugin) -> None:
    """Test handling of jc parsing failure."""

    def mock_cmd(command, task_vars=None):
        return {"rc": 0, "stdout": "invalid output", "stderr": ""}

    def mock_jc_parse(parser, data, quiet=True, raw=False):
        raise ValueError("Parse error")

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)
    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.action.process.jc_parse",
        mock_jc_parse,
    )

    plugin._task.args = {}
    result = plugin.run(task_vars={})

    assert result["failed"] is True
    assert "Failed to parse ps output" in result["msg"]
    assert result["processes"] == []


def test_process_connection_failure_propagates(monkeypatch, plugin) -> None:
    """Test that connection failures are properly propagated."""

    def mock_super_run(tmp, task_vars):
        raise AnsibleConnectionFailure("connection lost")

    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.module_utils.posix_action_base.PosixActionBase.run",
        mock_super_run,
    )

    with pytest.raises(AnsibleConnectionFailure):
        plugin.run(tmp=None, task_vars={})


def test_process_singular_aliases(monkeypatch, plugin) -> None:
    """Test that singular aliases (pid, executable) work."""

    def mock_cmd(command, task_vars=None):
        return {"rc": 0, "stdout": "", "stderr": ""}

    def mock_jc_parse(parser, data, quiet=True, raw=False):
        return [
            {"pid": 100, "command": "/usr/sbin/sshd -D"},
            {"pid": 200, "command": "/usr/sbin/httpd"},
        ]

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)
    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.action.process.jc_parse",
        mock_jc_parse,
    )

    # Test singular aliases
    plugin._task.args = {"pid": 100, "executable": "sshd"}
    result = plugin.run(task_vars={})

    # Should match both pid=100 (httpd not matched by executable filter would be excluded)
    # and executable=sshd
    assert len(result["processes"]) == 1
    assert result["processes"][0]["pid"] == 100
