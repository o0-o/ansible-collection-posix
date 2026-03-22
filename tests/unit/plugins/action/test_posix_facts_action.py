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

"""Unit tests for facts action plugin."""

from __future__ import annotations

from typing import Generator

import pytest

from ansible.errors import AnsibleActionFail, AnsibleConnectionFailure
from ansible_collections.o0_o.posix.plugins.action.facts import (
    ActionModule,
)


@pytest.fixture
def plugin(base) -> Generator[ActionModule, None, None]:
    """Create an ActionModule instance with patched dependencies."""
    base._task.async_val = False
    base._task.action = "facts"
    base._task.args = {}

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
    plugin.inventory_hostname = "localhost"
    return plugin


class TestResolveSubsets:
    """Tests for _resolve_subsets method."""

    def test_all(self, plugin) -> None:
        """Test subset resolution for 'all'."""
        selected = plugin._resolve_subsets(["all"])
        assert "uname" in selected
        assert "locale" in selected
        assert "timezone" in selected
        assert "hardware" in selected
        assert "compliance" in selected

    def test_min(self, plugin) -> None:
        """Test subset resolution for 'min'."""
        selected = plugin._resolve_subsets(["min"])
        assert selected == {
            "uname",
            "locale",
            "timezone",
            "compliance",
        }

    def test_storage(self, plugin) -> None:
        """Test subset resolution for 'storage' group."""
        selected = plugin._resolve_subsets(["storage"])
        assert selected == {"mounts", "fstab"}

    def test_exclusion(self, plugin) -> None:
        """Test subset exclusion with !subset."""
        selected = plugin._resolve_subsets(["all", "!hardware"])
        assert "uname" in selected
        assert "hardware" not in selected

    def test_exclude_all_then_add(self, plugin) -> None:
        """Test !all followed by specific subsets."""
        selected = plugin._resolve_subsets(["all", "!all", "uname"])
        assert selected == {"uname"}

    def test_only_exclusions_starts_from_all(self, plugin) -> None:
        """Test that only exclusions start from full set."""
        selected = plugin._resolve_subsets(["!hardware"])
        assert "uname" in selected
        assert "hardware" not in selected

    def test_invalid(self, plugin) -> None:
        """Test invalid subset raises error."""
        with pytest.raises(AnsibleActionFail, match="Invalid gather_subset"):
            plugin._resolve_subsets(["invalid_subset"])


class TestGatherMethods:
    """Tests for individual _gather_* methods."""

    def test_gather_uname(self, monkeypatch, plugin) -> None:
        """Test _gather_uname parses uname output."""
        from ansible_collections.o0_o.posix.plugins.action import (
            facts as facts_mod,
        )

        def mock_parse(output, e_prefix):
            return (
                {
                    "kernel": {"name": "linux", "pretty": "Linux"},
                    "hostname": {"short": "host"},
                    "architecture": "x86_64",
                },
                [],
            )

        monkeypatch.setattr(facts_mod, "_parse_uname", mock_parse)

        def mock_command(cmd, task_vars=None, **kwargs):
            return {"rc": 0, "stdout": "Linux host 5.15.0"}

        monkeypatch.setattr(plugin, "_command", mock_command)

        result = plugin._gather_uname(task_vars={})
        assert result["o0_os"]["kernel"]["name"] == "linux"
        assert result["o0_network"]["hostname"]["short"] == "host"
        assert result["o0_hardware"]["baseboard"]["architecture"] == "x86_64"

    def test_gather_uname_empty_returns_empty(
        self, monkeypatch, plugin
    ) -> None:
        """Test _gather_uname returns empty on parse failure."""
        from ansible_collections.o0_o.posix.plugins.action import (
            facts as facts_mod,
        )

        def mock_parse(output, e_prefix):
            return None, [ValueError("empty")]

        monkeypatch.setattr(facts_mod, "_parse_uname", mock_parse)

        def mock_command(cmd, task_vars=None, **kwargs):
            return {"rc": 0, "stdout": ""}

        monkeypatch.setattr(plugin, "_command", mock_command)

        result = plugin._gather_uname(task_vars={})
        assert result == {}

    def test_gather_compliance(self, monkeypatch, plugin) -> None:
        """Test _gather_compliance delegates to compliance module."""

        def mock_execute(module_name, module_args, task_vars=None):
            if module_name == "o0_o.posix.compliance":
                return {"compliance": {"posix": {"supported": True}}}
            return {}

        monkeypatch.setattr(plugin, "_execute_module", mock_execute)

        result = plugin._gather_compliance(task_vars={})
        assert result["o0_os"]["compliance"]["posix"]["supported"] is True

    def test_gather_compliance_failure_returns_empty(
        self, monkeypatch, plugin
    ) -> None:
        """Test _gather_compliance returns empty on failure."""

        def mock_execute(module_name, module_args, task_vars=None):
            return {"failed": True}

        monkeypatch.setattr(plugin, "_execute_module", mock_execute)

        result = plugin._gather_compliance(task_vars={})
        assert result == {}


class TestRun:
    """Tests for the full run() method."""

    def test_connection_failure_propagates(self, monkeypatch, plugin) -> None:
        """Test that connection failures are propagated."""
        plugin._task.args = {"gather_subset": ["uname"]}

        def mock_command(cmd, task_vars=None, **kwargs):
            raise AnsibleConnectionFailure("connection lost")

        monkeypatch.setattr(plugin, "_command", mock_command)

        with pytest.raises(AnsibleConnectionFailure):
            plugin.run(tmp=None, task_vars={})

    def test_subset_failure_warns(self, monkeypatch, plugin) -> None:
        """Test that subset failures emit warnings, not errors."""
        plugin._task.args = {"gather_subset": ["hardware"]}

        def mock_command(cmd, task_vars=None, **kwargs):
            raise RuntimeError("dmidecode not found")

        monkeypatch.setattr(plugin, "_command", mock_command)

        result = plugin.run(tmp=None, task_vars={})
        assert result["changed"] is False
        assert "ansible_facts" in result
        plugin._display.warning.assert_called()

    def test_result_has_invocation(self, monkeypatch, plugin) -> None:
        """Test that result includes invocation."""
        plugin._task.args = {"gather_subset": ["!all", "uname"]}

        from ansible_collections.o0_o.posix.plugins.action import (
            facts as facts_mod,
        )

        def mock_parse(output, e_prefix):
            return (
                {"kernel": {"name": "linux"}},
                [],
            )

        monkeypatch.setattr(facts_mod, "_parse_uname", mock_parse)

        def mock_command(cmd, task_vars=None, **kwargs):
            return {"rc": 0, "stdout": "Linux"}

        monkeypatch.setattr(plugin, "_command", mock_command)

        result = plugin.run(tmp=None, task_vars={})
        assert "invocation" in result

    def test_changed_is_false(self, monkeypatch, plugin) -> None:
        """Test that changed is always false."""
        plugin._task.args = {"gather_subset": ["!all"]}

        result = plugin.run(tmp=None, task_vars={})
        assert result["changed"] is False
