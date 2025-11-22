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

from ansible.errors import AnsibleActionFail


@pytest.fixture
def stat_plugin():
    """Create a stat ActionModule instance for testing.

    Provides a configured stat action plugin with mocked Ansible
    dependencies for unit testing the orchestration logic.
    """
    from ansible_collections.o0_o.posix.plugins.action.stat import (
        ActionModule,
    )

    plugin = ActionModule(
        task=MagicMock(),
        connection=MagicMock(),
        play_context=MagicMock(),
        loader=MagicMock(),
        templar=MagicMock(),
        shared_loader_obj=MagicMock(),
    )

    # Add display mock
    plugin._display = MagicMock()

    # Initialize inventory_hostname
    plugin.inventory_hostname = "localhost"

    # Mock validate_argument_spec to return test arguments
    plugin.validate_argument_spec = MagicMock()

    return plugin


def test_stat_orchestration_success(stat_plugin, monkeypatch):
    """Test successful stat orchestration through both stages."""
    # Setup argument validation
    test_args = {
        "path": "/tmp/testfile",
        "follow": False,
        "get_checksum": True,
        "get_mime": True,
        "get_attributes": True,
        "checksum_algorithm": "sha256",
        "_force_raw": False,
    }
    stat_plugin.validate_argument_spec.return_value = (None, test_args)

    # Mock _def_inventory_hostname
    stat_plugin._def_inventory_hostname = MagicMock()

    # Mock super().run()
    def mock_super_run(self, tmp, task_vars):
        return {"changed": False, "invocation": {}}

    monkeypatch.setattr(
        "ansible.plugins.action.ActionBase.run", mock_super_run
    )

    # Mock stage 1 methods
    stage1_commands = [
        ("stat_main", ["stat", "/tmp/testfile"]),
        ("readlink", ["readlink", "/tmp/testfile"]),
    ]
    stat_plugin._get_stat_commands_stage1 = MagicMock(
        return_value=stage1_commands
    )

    stage1_result = {
        "failed": False,
        "commands": [
            {"rc": 0, "stdout": "stat output"},
            {"rc": 1, "stdout": ""},
        ],
    }
    stat_plugin._run = MagicMock(return_value=stage1_result)

    partial_stat = {"exists": True, "path": "/tmp/testfile"}
    stage2_params = {
        "username": "testuser",
        "groupname": "testgroup",
        "is_symlink": False,
        "file_type_char": "-",
        "is_regular_file": True,
    }
    stat_plugin._process_stat_stage1 = MagicMock(
        return_value=(partial_stat, stage2_params)
    )

    # Mock stage 2 methods
    stage2_commands = [
        ("uid", ["id", "-u", "testuser"]),
        ("gid", ["id", "-g", "testuser"]),
    ]
    stat_plugin._get_stat_commands_stage2 = MagicMock(
        return_value=stage2_commands
    )

    final_stat = {
        "exists": True,
        "path": "/tmp/testfile",
        "uid": 1000,
        "gid": 1000,
        "mode": "0644",
    }
    stat_plugin._process_stat_stage2 = MagicMock(return_value=final_stat)

    # Execute
    stat_plugin._task.args = test_args.copy()
    result = stat_plugin.run(tmp=None, task_vars={})

    # Verify orchestration
    assert result["stat"] == final_stat
    assert result["changed"] is False

    # Verify stage 1 execution
    stat_plugin._get_stat_commands_stage1.assert_called_once_with(
        "/tmp/testfile", True
    )
    assert stat_plugin._run.call_count == 2  # Stage 1 and Stage 2

    # Verify stage 1 processing
    stat_plugin._process_stat_stage1.assert_called_once()

    # Verify stage 2 execution
    stat_plugin._get_stat_commands_stage2.assert_called_once_with(
        path="/tmp/testfile",
        username="testuser",
        groupname="testgroup",
        is_symlink=False,
        follow=False,
        file_type_char="-",
        is_regular_file=True,
        get_checksum=True,
        checksum_algorithm="sha256",
        get_attributes=True,
    )

    # Verify stage 2 processing
    stat_plugin._process_stat_stage2.assert_called_once()


def test_stat_file_not_exists(stat_plugin, monkeypatch):
    """Test stat early returns when file doesn't exist."""
    test_args = {
        "path": "/tmp/nonexistent",
        "follow": False,
        "get_checksum": True,
        "get_mime": True,
        "get_attributes": True,
        "checksum_algorithm": "sha1",
        "_force_raw": False,
    }
    stat_plugin.validate_argument_spec.return_value = (None, test_args)
    stat_plugin._def_inventory_hostname = MagicMock()

    def mock_super_run(self, tmp, task_vars):
        return {"changed": False, "invocation": {}}

    monkeypatch.setattr(
        "ansible.plugins.action.ActionBase.run", mock_super_run
    )

    # Mock stage 1
    stat_plugin._get_stat_commands_stage1 = MagicMock(
        return_value=[("stat_main", ["stat", "/tmp/nonexistent"])]
    )
    stat_plugin._run = MagicMock(
        return_value={
            "failed": False,
            "commands": [{"rc": 1, "stdout": ""}],
        }
    )

    # File doesn't exist
    partial_stat = {"exists": False}
    stat_plugin._process_stat_stage1 = MagicMock(
        return_value=(partial_stat, {})
    )

    stat_plugin._task.args = test_args.copy()
    result = stat_plugin.run(tmp=None, task_vars={})

    # Should return early without calling stage 2
    assert result["stat"]["exists"] is False
    assert stat_plugin._run.call_count == 1  # Only stage 1


def test_stat_process_stage1_error(stat_plugin, monkeypatch):
    """Test stat handles processing errors in stage 1."""
    test_args = {
        "path": "/tmp/testfile",
        "follow": False,
        "get_checksum": True,
        "get_mime": True,
        "get_attributes": True,
        "checksum_algorithm": "sha1",
        "_force_raw": False,
    }
    stat_plugin.validate_argument_spec.return_value = (None, test_args)
    stat_plugin._def_inventory_hostname = MagicMock()

    def mock_super_run(self, tmp, task_vars):
        return {"changed": False, "invocation": {}}

    monkeypatch.setattr(
        "ansible.plugins.action.ActionBase.run", mock_super_run
    )

    stat_plugin._get_stat_commands_stage1 = MagicMock(
        return_value=[("stat_main", ["stat", "/tmp/testfile"])]
    )
    stat_plugin._run = MagicMock(
        return_value={
            "failed": False,
            "commands": [{"rc": 0, "stdout": "invalid"}],
        }
    )

    # Process stage 1 raises ValueError
    stat_plugin._process_stat_stage1 = MagicMock(
        side_effect=ValueError("Invalid jc output")
    )

    stat_plugin._task.args = test_args.copy()

    with pytest.raises(AnsibleActionFail, match="Invalid jc output"):
        stat_plugin.run(tmp=None, task_vars={})


def test_stat_process_stage2_error(stat_plugin, monkeypatch):
    """Test stat handles processing errors in stage 2."""
    test_args = {
        "path": "/tmp/testfile",
        "follow": False,
        "get_checksum": True,
        "get_mime": True,
        "get_attributes": True,
        "checksum_algorithm": "sha1",
        "_force_raw": False,
    }
    stat_plugin.validate_argument_spec.return_value = (None, test_args)
    stat_plugin._def_inventory_hostname = MagicMock()

    def mock_super_run(self, tmp, task_vars):
        return {"changed": False, "invocation": {}}

    monkeypatch.setattr(
        "ansible.plugins.action.ActionBase.run", mock_super_run
    )

    # Mock stage 1 success
    stat_plugin._get_stat_commands_stage1 = MagicMock(
        return_value=[("stat_main", ["stat", "/tmp/testfile"])]
    )
    stat_plugin._run = MagicMock(
        return_value={
            "failed": False,
            "commands": [{"rc": 0, "stdout": ""}],
        }
    )

    partial_stat = {"exists": True}
    stage2_params = {
        "username": "root",
        "groupname": "root",
        "is_symlink": False,
        "file_type_char": "-",
        "is_regular_file": True,
    }
    stat_plugin._process_stat_stage1 = MagicMock(
        return_value=(partial_stat, stage2_params)
    )
    stat_plugin._get_stat_commands_stage2 = MagicMock(
        return_value=[("uid", ["id", "-u", "root"])]
    )

    # Process stage 2 raises RuntimeError
    stat_plugin._process_stat_stage2 = MagicMock(
        side_effect=RuntimeError("Failed to parse uid")
    )

    stat_plugin._task.args = test_args.copy()

    with pytest.raises(AnsibleActionFail, match="Failed to parse uid"):
        stat_plugin.run(tmp=None, task_vars={})


@pytest.mark.parametrize(
    "get_checksum,get_mime,get_attributes,algorithm",
    [
        (True, True, True, "sha256"),
        (False, True, True, "sha1"),
        (True, False, True, "md5"),
        (True, True, False, "sha512"),
        (False, False, False, "sha1"),
    ],
)
def test_stat_parameter_variations(
    stat_plugin,
    monkeypatch,
    get_checksum,
    get_mime,
    get_attributes,
    algorithm,
):
    """Test stat correctly passes parameters through orchestration."""
    test_args = {
        "path": "/tmp/testfile",
        "follow": True,
        "get_checksum": get_checksum,
        "get_mime": get_mime,
        "get_attributes": get_attributes,
        "checksum_algorithm": algorithm,
        "_force_raw": False,
    }
    stat_plugin.validate_argument_spec.return_value = (None, test_args)
    stat_plugin._def_inventory_hostname = MagicMock()

    def mock_super_run(self, tmp, task_vars):
        return {"changed": False, "invocation": {}}

    monkeypatch.setattr(
        "ansible.plugins.action.ActionBase.run", mock_super_run
    )

    # Mock all methods
    stat_plugin._get_stat_commands_stage1 = MagicMock(
        return_value=[("stat_main", ["stat", "/tmp/testfile"])]
    )
    stat_plugin._run = MagicMock(
        return_value={
            "failed": False,
            "commands": [{"rc": 0, "stdout": ""}],
        }
    )
    partial_stat = {"exists": True}
    stage2_params = {
        "username": "user",
        "groupname": "group",
        "is_symlink": False,
        "file_type_char": "-",
        "is_regular_file": True,
    }
    stat_plugin._process_stat_stage1 = MagicMock(
        return_value=(partial_stat, stage2_params)
    )
    stat_plugin._get_stat_commands_stage2 = MagicMock(
        return_value=[("uid", ["id", "-u", "user"])]
    )
    stat_plugin._process_stat_stage2 = MagicMock(
        return_value={"exists": True, "path": "/tmp/testfile"}
    )

    stat_plugin._task.args = test_args.copy()
    stat_plugin.run(tmp=None, task_vars={})

    # Verify parameters passed to stage 1
    stat_plugin._get_stat_commands_stage1.assert_called_once_with(
        "/tmp/testfile", get_mime
    )

    # Verify parameters passed to stage 2
    call_args = stat_plugin._get_stat_commands_stage2.call_args
    assert call_args.kwargs["get_checksum"] == get_checksum
    assert call_args.kwargs["checksum_algorithm"] == algorithm
    assert call_args.kwargs["get_attributes"] == get_attributes
    assert call_args.kwargs["follow"] is True

    # Verify parameters passed to processing
    process_call = stat_plugin._process_stat_stage2.call_args
    assert process_call.kwargs["get_checksum"] == get_checksum
    assert process_call.kwargs["checksum_algorithm"] == algorithm
    assert process_call.kwargs["get_mime"] == get_mime
    assert process_call.kwargs["get_attributes"] == get_attributes
