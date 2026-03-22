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


class TestMergeFacts:
    """Tests for _merge_facts helper."""

    def test_merge_new_namespace(self, plugin) -> None:
        """Test merging into empty accumulator."""
        acc = {}
        plugin._merge_facts(acc, {"o0_os": {"kernel": {"name": "linux"}}})
        assert acc == {"o0_os": {"kernel": {"name": "linux"}}}

    def test_merge_deep(self, plugin) -> None:
        """Test deep merge of nested dicts."""
        acc = {"o0_hardware": {"baseboard": {"arch": "x86_64"}}}
        plugin._merge_facts(
            acc,
            {"o0_hardware": {"baseboard": {"make": "Dell"}}},
        )
        assert acc["o0_hardware"]["baseboard"] == {
            "arch": "x86_64",
            "make": "Dell",
        }

    def test_merge_replaces_non_dict(self, plugin) -> None:
        """Test that non-dict values are replaced."""
        acc = {"o0_os": {"shells": ["old"]}}
        plugin._merge_facts(acc, {"o0_os": {"shells": ["new"]}})
        assert acc["o0_os"]["shells"] == ["new"]


class TestBatchedExecution:
    """Tests for the batched COMMAND_SPEC path."""

    def test_uname_in_batched_subsets(self, plugin) -> None:
        """Test uname is listed as a batched subset."""
        assert "uname" in plugin.BATCHED_SUBSETS

    def test_compliance_in_batched_subsets(self, plugin) -> None:
        """Test compliance is listed as a batched subset."""
        assert "compliance" in plugin.BATCHED_SUBSETS

    def test_batched_requests_callable(self, plugin) -> None:
        """Test that batched request functions are callable."""
        for subset, spec in plugin.BATCHED_SUBSETS.items():
            assert callable(spec["requests"])
            assert callable(spec["processor"])

    def test_run_batched_uname_only(self, monkeypatch, plugin) -> None:
        """Test run with only uname subset uses batched path."""
        plugin._task.args = {"gather_subset": ["!all", "uname"]}

        run_called = {}

        def mock_run(commands, **kwargs):
            run_called["commands"] = commands
            return []

        monkeypatch.setattr(plugin, "_run", mock_run)

        # Patch the processor in the BATCHED_SUBSETS dict
        mock_processor = lambda results: (
            {
                "o0_os": {"kernel": {"name": "linux"}},
                "o0_network": {"hostname": {"short": "host"}},
            },
            [],
        )
        monkeypatch.setitem(
            plugin.BATCHED_SUBSETS["uname"],
            "processor",
            mock_processor,
        )

        result = plugin.run(tmp=None, task_vars={})

        assert "commands" in run_called
        assert result["ansible_facts"]["o0_os"]["kernel"]["name"] == "linux"
        assert result["changed"] is False


class TestLegacyExecution:
    """Tests for the legacy gather method path."""

    def test_locale_in_legacy(self, plugin) -> None:
        """Test locale is listed as a legacy subset."""
        assert "locale" in plugin.LEGACY_METHODS

    def test_legacy_failure_warns(self, monkeypatch, plugin) -> None:
        """Test that legacy subset failures emit warnings."""
        plugin._task.args = {"gather_subset": ["!all", "hardware"]}

        def mock_command(cmd, task_vars=None, **kwargs):
            raise RuntimeError("dmidecode not found")

        monkeypatch.setattr(plugin, "_command", mock_command)

        result = plugin.run(tmp=None, task_vars={})
        assert result["changed"] is False
        assert "ansible_facts" in result
        plugin._display.warning.assert_called()


class TestRun:
    """Tests for the full run() method."""

    def test_connection_failure_propagates(self, monkeypatch, plugin) -> None:
        """Test that connection failures are propagated."""
        plugin._task.args = {"gather_subset": ["!all", "locale"]}

        def mock_command(cmd, task_vars=None, **kwargs):
            raise AnsibleConnectionFailure("connection lost")

        monkeypatch.setattr(plugin, "_command", mock_command)

        with pytest.raises(AnsibleConnectionFailure):
            plugin.run(tmp=None, task_vars={})

    def test_result_has_invocation(self, monkeypatch, plugin) -> None:
        """Test that result includes invocation."""
        plugin._task.args = {"gather_subset": ["!all"]}

        result = plugin.run(tmp=None, task_vars={})
        assert "invocation" in result

    def test_changed_is_false(self, monkeypatch, plugin) -> None:
        """Test that changed is always false."""
        plugin._task.args = {"gather_subset": ["!all"]}

        result = plugin.run(tmp=None, task_vars={})
        assert result["changed"] is False

    def test_empty_subset_returns_empty_facts(self, plugin) -> None:
        """Test that !all returns empty ansible_facts."""
        plugin._task.args = {"gather_subset": ["!all"]}

        result = plugin.run(tmp=None, task_vars={})
        assert result["ansible_facts"] == {}
