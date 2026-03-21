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

"""Unit tests for env action plugin."""

from __future__ import annotations

from typing import Generator

import pytest

from ansible_collections.o0_o.posix.plugins.action.env import (
    ActionModule,
)


@pytest.fixture
def plugin(base) -> Generator[ActionModule, None, None]:
    """Create an ActionModule instance for env collection tests."""
    base._task.async_val = False
    base._task.action = "env"
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
    return plugin


class TestBuildCommands:
    """Tests for _build_commands helper method."""

    def test_single_var(self, plugin) -> None:
        """Test command generation for a single variable."""
        cmds = plugin._build_commands(["HOME"])
        assert "HOME" in cmds
        assert cmds["HOME"] == "set -eu; printf '%s' \"${HOME}\""

    def test_multiple_vars(self, plugin) -> None:
        """Test command generation for multiple variables."""
        cmds = plugin._build_commands(["HOME", "SHELL", "TZ"])
        assert len(cmds) == 3
        assert cmds["TZ"] == "set -eu; printf '%s' \"${TZ}\""

    def test_empty_list(self, plugin) -> None:
        """Test command generation for empty variable list."""
        cmds = plugin._build_commands([])
        assert cmds == {}


class TestParseResults:
    """Tests for _parse_results helper method."""

    def test_dict_mode_set_var(self, plugin) -> None:
        """Test dict mode with a set variable."""
        run_results = {
            "HOME": {"rc": 0, "stdout": "/root"},
        }
        result = plugin._parse_results(["HOME"], run_results, False)
        assert result == {"HOME": "/root"}

    def test_dict_mode_unset_var(self, plugin) -> None:
        """Test dict mode with an unset variable returns None."""
        run_results = {
            "OLDPWD": {"rc": 1, "stdout": ""},
        }
        result = plugin._parse_results(["OLDPWD"], run_results, False)
        assert result == {"OLDPWD": None}

    def test_dict_mode_empty_string(self, plugin) -> None:
        """Test dict mode with a variable set to empty string."""
        run_results = {
            "TZ": {"rc": 0, "stdout": ""},
        }
        result = plugin._parse_results(["TZ"], run_results, False)
        assert result == {"TZ": ""}

    def test_dict_mode_mixed(self, plugin) -> None:
        """Test dict mode with mix of set, unset, and empty vars."""
        run_results = {
            "HOME": {"rc": 0, "stdout": "/home/user"},
            "TZ": {"rc": 0, "stdout": ""},
            "OLDPWD": {"rc": 1, "stdout": ""},
        }
        result = plugin._parse_results(
            ["HOME", "TZ", "OLDPWD"], run_results, False
        )
        assert result == {
            "HOME": "/home/user",
            "TZ": "",
            "OLDPWD": None,
        }

    def test_dict_mode_missing_key(self, plugin) -> None:
        """Test dict mode when run_results is missing a key."""
        result = plugin._parse_results(["MISSING"], {}, False)
        assert result == {"MISSING": None}

    def test_list_mode_set_var(self, plugin) -> None:
        """Test list mode with a set variable."""
        run_results = {
            "SHELL": {"rc": 0, "stdout": "/bin/bash"},
        }
        result = plugin._parse_results(["SHELL"], run_results, True)
        assert result == [{"SHELL": "/bin/bash"}]

    def test_list_mode_unset_var(self, plugin) -> None:
        """Test list mode with an unset variable returns None."""
        run_results = {
            "OLDPWD": {"rc": 1, "stdout": ""},
        }
        result = plugin._parse_results(["OLDPWD"], run_results, True)
        assert result == [{"OLDPWD": None}]

    def test_list_mode_mixed(self, plugin) -> None:
        """Test list mode with mixed set/unset variables."""
        run_results = {
            "HOME": {"rc": 0, "stdout": "/root"},
            "OLDPWD": {"rc": 1, "stdout": ""},
        }
        result = plugin._parse_results(["HOME", "OLDPWD"], run_results, True)
        assert result == [
            {"HOME": "/root"},
            {"OLDPWD": None},
        ]

    def test_list_mode_preserves_order(self, plugin) -> None:
        """Test list mode preserves input variable order."""
        run_results = {
            "C": {"rc": 0, "stdout": "c"},
            "A": {"rc": 0, "stdout": "a"},
            "B": {"rc": 0, "stdout": "b"},
        }
        result = plugin._parse_results(["A", "B", "C"], run_results, True)
        assert result == [
            {"A": "a"},
            {"B": "b"},
            {"C": "c"},
        ]


class TestRunIntegration:
    """Tests for the full run() method with mocked _run."""

    def test_single_var_dict(self, monkeypatch, plugin) -> None:
        """Test collecting a single variable in dict mode."""
        plugin._task.args = {"env": ["HOME"]}

        def mock_run(commands, **kwargs):
            return {
                "HOME": {"rc": 0, "stdout": "/root"},
            }

        monkeypatch.setattr(plugin, "_run", mock_run)
        result = plugin.run(task_vars={})
        assert result["env"] == {"HOME": "/root"}
        assert result["changed"] is False

    def test_multiple_vars_dict(self, monkeypatch, plugin) -> None:
        """Test collecting multiple variables in dict mode."""
        plugin._task.args = {
            "env": ["HOME", "SHELL", "TZ"],
        }

        def mock_run(commands, **kwargs):
            return {
                "HOME": {"rc": 0, "stdout": "/home/user"},
                "SHELL": {"rc": 0, "stdout": "/bin/sh"},
                "TZ": {"rc": 0, "stdout": "UTC"},
            }

        monkeypatch.setattr(plugin, "_run", mock_run)
        result = plugin.run(task_vars={})
        assert result["env"] == {
            "HOME": "/home/user",
            "SHELL": "/bin/sh",
            "TZ": "UTC",
        }

    def test_unset_var_returns_none(self, monkeypatch, plugin) -> None:
        """Test that unset variables are returned as None."""
        plugin._task.args = {"env": ["TZ"]}

        def mock_run(commands, **kwargs):
            return {
                "TZ": {"rc": 1, "stdout": ""},
            }

        monkeypatch.setattr(plugin, "_run", mock_run)
        result = plugin.run(task_vars={})
        assert result["env"]["TZ"] is None

    def test_empty_var_returns_empty_string(self, monkeypatch, plugin) -> None:
        """Test that empty variables are returned as empty string."""
        plugin._task.args = {"env": ["LC_ALL"]}

        def mock_run(commands, **kwargs):
            return {
                "LC_ALL": {"rc": 0, "stdout": ""},
            }

        monkeypatch.setattr(plugin, "_run", mock_run)
        result = plugin.run(task_vars={})
        assert result["env"]["LC_ALL"] == ""

    def test_wantlist_mode(self, monkeypatch, plugin) -> None:
        """Test list output mode when wantlist=true."""
        plugin._task.args = {
            "env": ["HOME", "SHELL"],
            "wantlist": True,
        }

        def mock_run(commands, **kwargs):
            return {
                "HOME": {"rc": 0, "stdout": "/root"},
                "SHELL": {"rc": 0, "stdout": "/bin/sh"},
            }

        monkeypatch.setattr(plugin, "_run", mock_run)
        result = plugin.run(task_vars={})
        assert result["env"] == [
            {"HOME": "/root"},
            {"SHELL": "/bin/sh"},
        ]

    def test_msg_contains_count(self, monkeypatch, plugin) -> None:
        """Test that msg includes variable count."""
        plugin._task.args = {"env": ["HOME", "TZ"]}

        def mock_run(commands, **kwargs):
            return {
                "HOME": {"rc": 0, "stdout": "/root"},
                "TZ": {"rc": 0, "stdout": "UTC"},
            }

        monkeypatch.setattr(plugin, "_run", mock_run)
        result = plugin.run(task_vars={})
        assert "2" in result["msg"]

    def test_invocation_set(self, monkeypatch, plugin) -> None:
        """Test that invocation contains the original args."""
        plugin._task.args = {"env": ["HOME"]}

        def mock_run(commands, **kwargs):
            return {
                "HOME": {"rc": 0, "stdout": "/root"},
            }

        monkeypatch.setattr(plugin, "_run", mock_run)
        result = plugin.run(task_vars={})
        assert result["invocation"] == {"env": ["HOME"]}

    def test_run_passes_parallel_and_check_mode(
        self, monkeypatch, plugin
    ) -> None:
        """Test that _run is called with correct kwargs."""
        plugin._task.args = {"env": ["HOME"]}
        captured = {}

        def mock_run(commands, **kwargs):
            captured.update(kwargs)
            return {
                "HOME": {"rc": 0, "stdout": "/root"},
            }

        monkeypatch.setattr(plugin, "_run", mock_run)
        plugin.run(task_vars={})
        assert captured["parallel"] is True
        assert captured["fail_fast"] is False
        assert captured["check_mode"] is False
