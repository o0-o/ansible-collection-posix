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

from ansible.errors import AnsibleActionFail, AnsibleConnectionFailure
from ansible_collections.o0_o.posix.plugins.action.facts import ActionModule


@pytest.fixture
def plugin(base) -> Generator[ActionModule, None, None]:
    """Create an ActionModule instance with patched dependencies."""
    base._task.async_val = False
    base._task.action = "facts"

    plugin = ActionModule(
        task=base._task,
        connection=base._connection,
        play_context=base._play_context,
        loader=base._loader,
        templar=base._templar,
        shared_loader_obj=base._shared_loader_obj,
    )
    plugin._cmd = base._cmd
    plugin._display = base._display
    return plugin


def test_resolve_subsets_all(plugin) -> None:
    """Test subset resolution for 'all'."""
    selected = plugin._resolve_subsets(["all"])
    assert "uname" in selected
    assert "locale" in selected
    assert "timezone" in selected
    assert "hardware" in selected
    assert "compliance" in selected


def test_resolve_subsets_min(plugin) -> None:
    """Test subset resolution for 'min'."""
    selected = plugin._resolve_subsets(["min"])
    assert selected == {"uname", "locale", "timezone", "compliance"}


def test_resolve_subsets_storage(plugin) -> None:
    """Test subset resolution for 'storage' group."""
    selected = plugin._resolve_subsets(["storage"])
    assert selected == {"mounts", "fstab"}


def test_resolve_subsets_exclusion(plugin) -> None:
    """Test subset exclusion with !subset."""
    selected = plugin._resolve_subsets(["all", "!hardware"])
    assert "uname" in selected
    assert "hardware" not in selected


def test_resolve_subsets_invalid(plugin) -> None:
    """Test invalid subset raises error."""
    with pytest.raises(AnsibleActionFail, match="Invalid gather_subset"):
        plugin._resolve_subsets(["invalid_subset"])


def test_run_skips_non_posix(monkeypatch, plugin) -> None:
    """Test that non-POSIX systems are skipped gracefully."""

    def mock_execute_module(module_name, module_args, task_vars=None):
        if module_name == "o0_o.posix.compliance":
            # Return compliance dict with posix key but no components
            # (indicates non-POSIX system per is_posix logic)
            return {"compliance": {"posix": {}}}
        return {}

    # Mock _execute_module to return non-POSIX compliance
    monkeypatch.setattr(plugin, "_execute_module", mock_execute_module)

    plugin._task.args = {"gather_subset": ["all"]}
    result = plugin.run(tmp=None, task_vars={})

    assert result.get("skipped") is True
    assert "POSIX" in result.get("skip_reason", "")


def test_run_connection_failure_propagates(monkeypatch, plugin) -> None:
    """Test that connection failures are properly propagated."""

    def mock_execute_module(module_name, module_args, task_vars=None):
        raise AnsibleConnectionFailure("connection lost")

    monkeypatch.setattr(plugin, "_execute_module", mock_execute_module)

    with pytest.raises(AnsibleConnectionFailure):
        plugin.run(tmp=None, task_vars={})
