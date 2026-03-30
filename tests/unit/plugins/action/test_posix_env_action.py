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


class TestProcessEnvResults:
    """Tests for process_env_command_results."""

    def test_dict_mode_set_var(self) -> None:
        """Test dict mode with a set variable."""
        from ansible_collections.o0_o.posix.plugins.module_utils.env_utils import (  # noqa: E501
            process_env_command_results,
        )

        results = [
            {
                "implementation": "posix",
                "type": "env_var",
                "args": {"env": "HOME"},
                "rc": 0,
                "stdout": "/root",
                "stderr": "",
                "parsed": "/root",
                "errors": [],
            }
        ]
        data = process_env_command_results(results, ["HOME"], False)
        assert data == {"HOME": "/root"}

    def test_dict_mode_unset_var_excluded(self) -> None:
        """Test dict mode excludes unset variables by default."""
        from ansible_collections.o0_o.posix.plugins.module_utils.env_utils import (  # noqa: E501
            process_env_command_results,
        )

        results = [
            {
                "implementation": "posix",
                "type": "env_var",
                "args": {"env": "OLDPWD"},
                "rc": 1,
                "stdout": "",
                "stderr": "",
                "parsed": None,
                "errors": [],
            }
        ]
        data = process_env_command_results(results, ["OLDPWD"], False)
        assert data == {}

    def test_dict_mode_unset_var_null(self) -> None:
        """Test dict mode includes unset vars as None when
        include_undefined is True."""
        from ansible_collections.o0_o.posix.plugins.module_utils.env_utils import (  # noqa: E501
            process_env_command_results,
        )

        results = [
            {
                "implementation": "posix",
                "type": "env_var",
                "args": {"env": "OLDPWD"},
                "rc": 1,
                "stdout": "",
                "stderr": "",
                "parsed": None,
                "errors": [],
            }
        ]
        data = process_env_command_results(results, ["OLDPWD"], False, True)
        assert data == {"OLDPWD": None}

    def test_list_mode(self) -> None:
        """Test list mode returns list of single-key dicts."""
        from ansible_collections.o0_o.posix.plugins.module_utils.env_utils import (  # noqa: E501
            process_env_command_results,
        )

        results = [
            {
                "implementation": "posix",
                "type": "env_var",
                "args": {"env": "HOME"},
                "rc": 0,
                "stdout": "/root",
                "stderr": "",
                "parsed": "/root",
                "errors": [],
            },
            {
                "implementation": "posix",
                "type": "env_var",
                "args": {"env": "SHELL"},
                "rc": 0,
                "stdout": "/bin/sh",
                "stderr": "",
                "parsed": "/bin/sh",
                "errors": [],
            },
        ]
        data = process_env_command_results(results, ["HOME", "SHELL"], True)
        assert data == [
            {"HOME": "/root"},
            {"SHELL": "/bin/sh"},
        ]

    def test_preserves_order(self) -> None:
        """Test that output preserves input variable order."""
        from ansible_collections.o0_o.posix.plugins.module_utils.env_utils import (  # noqa: E501
            process_env_command_results,
        )

        results = [
            {
                "implementation": "posix",
                "type": "env_var",
                "args": {"env": "B"},
                "rc": 0,
                "stdout": "b",
                "stderr": "",
                "parsed": "b",
                "errors": [],
            },
            {
                "implementation": "posix",
                "type": "env_var",
                "args": {"env": "A"},
                "rc": 0,
                "stdout": "a",
                "stderr": "",
                "parsed": "a",
                "errors": [],
            },
        ]
        data = process_env_command_results(results, ["A", "B"], False)
        assert list(data.keys()) == ["A", "B"]


class TestRunIntegration:
    """Tests for the full run() method with mocked _run."""

    def test_single_var_dict(self, monkeypatch, plugin) -> None:
        """Test collecting a single variable in dict mode."""
        plugin._task.args = {"env": ["HOME"]}

        def mock_run(commands, **kwargs):
            return [
                {
                    "implementation": "posix",
                    "type": "env_var",
                    "args": {"env": "HOME"},
                    "rc": 0,
                    "stdout": "/root",
                    "stderr": "",
                }
            ]

        monkeypatch.setattr(plugin, "_run", mock_run)
        result = plugin.run(task_vars={})
        assert result["env"] == {"HOME": "/root"}
        assert result["changed"] is False

    def test_unset_var_excluded_by_default(self, monkeypatch, plugin) -> None:
        """Test that unset variables are excluded by default."""
        plugin._task.args = {"env": ["TZ"]}

        def mock_run(commands, **kwargs):
            return [
                {
                    "implementation": "posix",
                    "type": "env_var",
                    "args": {"env": "TZ"},
                    "rc": 1,
                    "stdout": "",
                    "stderr": "sh: TZ: unbound variable",
                }
            ]

        monkeypatch.setattr(plugin, "_run", mock_run)
        result = plugin.run(task_vars={})
        assert "TZ" not in result["env"]

    def test_unset_var_null_when_requested(self, monkeypatch, plugin) -> None:
        """Test that unset variables return None with
        undefined=null."""
        plugin._task.args = {
            "env": ["TZ"],
            "undefined": "null",
        }

        def mock_run(commands, **kwargs):
            return [
                {
                    "implementation": "posix",
                    "type": "env_var",
                    "args": {"env": "TZ"},
                    "rc": 1,
                    "stdout": "",
                    "stderr": "sh: TZ: unbound variable",
                }
            ]

        monkeypatch.setattr(plugin, "_run", mock_run)
        result = plugin.run(task_vars={})
        assert result["env"]["TZ"] is None

    def test_wantlist_mode(self, monkeypatch, plugin) -> None:
        """Test list output mode when wantlist=true."""
        plugin._task.args = {
            "env": ["HOME", "SHELL"],
            "wantlist": True,
        }

        def mock_run(commands, **kwargs):
            return [
                {
                    "implementation": "posix",
                    "type": "env_var",
                    "args": {"env": "HOME"},
                    "rc": 0,
                    "stdout": "/root",
                    "stderr": "",
                },
                {
                    "implementation": "posix",
                    "type": "env_var",
                    "args": {"env": "SHELL"},
                    "rc": 0,
                    "stdout": "/bin/sh",
                    "stderr": "",
                },
            ]

        monkeypatch.setattr(plugin, "_run", mock_run)
        result = plugin.run(task_vars={})
        assert result["env"] == [
            {"HOME": "/root"},
            {"SHELL": "/bin/sh"},
        ]

    def test_run_passes_correct_kwargs(self, monkeypatch, plugin) -> None:
        """Test that _run is called with correct kwargs."""
        plugin._task.args = {"env": ["HOME"]}
        captured = {}

        def mock_run(commands, **kwargs):
            captured.update(kwargs)
            return [
                {
                    "implementation": "posix",
                    "type": "env_var",
                    "args": {"env": "HOME"},
                    "rc": 0,
                    "stdout": "/root",
                    "stderr": "",
                }
            ]

        monkeypatch.setattr(plugin, "_run", mock_run)
        plugin.run(task_vars={})
        assert captured["parallel"] is True
        assert captured["fail_fast"] is False
        assert captured["check_mode"] is False
