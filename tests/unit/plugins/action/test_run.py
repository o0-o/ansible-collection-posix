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

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def plugin():
    """Create run ActionModule instance with patched dependencies."""
    from ansible_collections.o0_o.posix.plugins.action.run import ActionModule

    task = MagicMock()
    task.async_val = 0
    task.check_mode = False

    action = ActionModule(
        task=task,
        connection=MagicMock(),
        play_context=MagicMock(),
        loader=MagicMock(),
        templar=MagicMock(),
        shared_loader_obj=MagicMock(),
    )
    action._display = MagicMock()
    action._make_tmp_path = MagicMock(return_value="/tmp/ansible-tmp-123")
    action._remove_tmp_path = MagicMock()
    action.inventory_hostname = "localhost"

    return action


def test_run_list_mode(plugin) -> None:
    """Test run with list input returns list output."""
    plugin._task.args = {
        "commands": ["echo foo", "echo bar"],
    }

    # Mock _cmd to return batch output
    def mock_cmd(cmd, **kwargs):
        return {
            "rc": 0,
            "raw": False,
            "stdout": "0\n7 /tmp/0.stdout\nfoo\n\n0 /tmp/0.stderr\n"
            "0\n7 /tmp/1.stdout\nbar\n\n0 /tmp/1.stderr\n\n",
            "stderr": "",
            "start": "2025-01-01 00:00:00",
            "end": "2025-01-01 00:00:01",
            "delta": "0:00:01",
        }

    plugin._cmd = mock_cmd

    result = plugin.run(task_vars={})

    assert result["changed"] is True
    assert isinstance(result["commands"], list)
    assert len(result["commands"]) == 2
    assert result["commands"][0]["cmd"] == "echo foo"
    assert result["commands"][1]["cmd"] == "echo bar"


def test_run_dict_mode(plugin) -> None:
    """Test run with dict input returns dict output."""
    plugin._task.args = {
        "commands": {"first": "echo foo", "second": "echo bar"},
    }

    # Mock _cmd to return batch output
    def mock_cmd(cmd, **kwargs):
        return {
            "rc": 0,
            "raw": False,
            "stdout": "0\n7 /tmp/0.stdout\nfoo\n\n0 /tmp/0.stderr\n"
            "0\n7 /tmp/1.stdout\nbar\n\n0 /tmp/1.stderr\n\n",
            "stderr": "",
            "start": "2025-01-01 00:00:00",
            "end": "2025-01-01 00:00:01",
            "delta": "0:00:01",
        }

    plugin._cmd = mock_cmd

    result = plugin.run(task_vars={})

    assert result["changed"] is True
    assert isinstance(result["commands"], dict)
    assert "first" in result["commands"]
    assert "second" in result["commands"]
    assert result["commands"]["first"]["cmd"] == "echo foo"
    assert result["commands"]["second"]["cmd"] == "echo bar"


def test_run_dict_mode_preserves_keys(plugin) -> None:
    """Test dict mode preserves all keys from input."""
    plugin._task.args = {
        "commands": {
            "kernel": "uname -s",
            "machine": "uname -m",
            "hostname": "hostname",
        },
    }

    # Mock _cmd to return batch output
    def mock_cmd(cmd, **kwargs):
        return {
            "rc": 0,
            "raw": False,
            "stdout": (
                "0\n10 /tmp/0.stdout\nLinux\n\n\n0 /tmp/0.stderr\n"
                "0\n11 /tmp/1.stdout\nx86_64\n\n\n0 /tmp/1.stderr\n"
                "0\n14 /tmp/2.stdout\ntesthost\n\n\n0 /tmp/2.stderr\n\n"
            ),
            "stderr": "",
            "start": "2025-01-01 00:00:00",
            "end": "2025-01-01 00:00:01",
            "delta": "0:00:01",
        }

    plugin._cmd = mock_cmd

    result = plugin.run(task_vars={})

    assert isinstance(result["commands"], dict)
    assert set(result["commands"].keys()) == {"kernel", "machine", "hostname"}
    assert result["commands"]["kernel"]["cmd"] == "uname -s"
    assert result["commands"]["machine"]["cmd"] == "uname -m"
    assert result["commands"]["hostname"]["cmd"] == "hostname"


def test_run_dict_mode_single_command(plugin) -> None:
    """Test dict mode with single command."""
    plugin._task.args = {
        "commands": {"only_one": "echo test"},
    }

    # Mock _cmd to return batch output
    def mock_cmd(cmd, **kwargs):
        return {
            "rc": 0,
            "raw": False,
            "stdout": "0\n9 /tmp/0.stdout\ntest\n\n\n0 /tmp/0.stderr\n\n",
            "stderr": "",
            "start": "2025-01-01 00:00:00",
            "end": "2025-01-01 00:00:01",
            "delta": "0:00:01",
        }

    plugin._cmd = mock_cmd

    result = plugin.run(task_vars={})

    assert isinstance(result["commands"], dict)
    assert len(result["commands"]) == 1
    assert "only_one" in result["commands"]
    assert result["commands"]["only_one"]["cmd"] == "echo test"


def test_run_dict_mode_with_failures(plugin) -> None:
    """Test dict mode properly handles command failures."""
    plugin._task.args = {
        "commands": {"pass": "true", "fail": "false"},
    }

    # Mock _cmd to return batch output with one failure
    def mock_cmd(cmd, **kwargs):
        return {
            "rc": 0,
            "raw": False,
            "stdout": (
                "0\n0 /tmp/0.stdout\n0 /tmp/0.stderr\n"
                "1\n0 /tmp/1.stdout\n0 /tmp/1.stderr\n\n"
            ),
            "stderr": "",
            "start": "2025-01-01 00:00:00",
            "end": "2025-01-01 00:00:01",
            "delta": "0:00:01",
        }

    plugin._cmd = mock_cmd

    result = plugin.run(task_vars={})

    assert result["failed"] is True
    assert isinstance(result["commands"], dict)
    assert result["commands"]["pass"]["rc"] == 0
    assert result["commands"]["fail"]["rc"] == 1
