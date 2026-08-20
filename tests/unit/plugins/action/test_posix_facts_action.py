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


def _mock_effective_uid(monkeypatch, uid) -> None:
    """Answer the batched ``id -u`` with a fixed uid."""
    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.action.facts."
        "process_effective_uid_results",
        lambda results: uid,
    )


@pytest.fixture
def plugin(monkeypatch, base) -> Generator[ActionModule, None, None]:
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
    monkeypatch.setattr(plugin, "_command", base._command)
    plugin._display = base._display
    plugin.inventory_hostname = "localhost"
    plugin.effective_user = "testuser"
    # Ensure _def_effective_user doesn't override our mock
    plugin._play_context.become = False
    plugin._play_context.remote_user = "testuser"
    plugin._play_context.connection_user = None
    return plugin


class TestResolveSubsets:
    """Tests for _resolve_subsets method."""

    def test_all(self, plugin) -> None:
        """Test subset resolution for 'all'."""
        selected = plugin._resolve_subsets(["all"])
        assert "uname" in selected
        assert "environment" in selected
        assert "dmidecode" in selected
        assert "compliance" in selected

    def test_min(self, plugin) -> None:
        """Test subset resolution for 'min'."""
        selected = plugin._resolve_subsets(["min"])
        assert selected == {
            "uname",
            "environment",
            "timezone",
            "compliance",
        }

    def test_storage(self, plugin) -> None:
        """Test subset resolution for 'storage' group."""
        selected = plugin._resolve_subsets(["storage"])
        assert selected == {"mounts", "fstab"}

    def test_exclusion(self, plugin) -> None:
        """Test subset exclusion with !subset."""
        selected = plugin._resolve_subsets(["all", "!dmidecode"])
        assert "uname" in selected
        assert "dmidecode" not in selected

    def test_exclude_all_then_add(self, plugin) -> None:
        """Test !all followed by specific subsets."""
        selected = plugin._resolve_subsets(["all", "!all", "uname"])
        assert selected == {"uname"}

    def test_only_exclusions_starts_from_all(self, plugin) -> None:
        """Test that only exclusions start from full set."""
        selected = plugin._resolve_subsets(["!dmidecode"])
        assert "uname" in selected
        assert "dmidecode" not in selected

    def test_invalid(self, plugin) -> None:
        """Test invalid subset raises error."""
        with pytest.raises(AnsibleActionFail, match="Invalid gather_subset"):
            plugin._resolve_subsets(["invalid_subset"])

    def test_locale_not_a_subset(self, plugin) -> None:
        """Test that locale is not a standalone subset."""
        with pytest.raises(AnsibleActionFail):
            plugin._resolve_subsets(["locale"])

    def test_timezone_subset(self, plugin) -> None:
        """Test that timezone is a valid subset."""
        selected = plugin._resolve_subsets(["timezone"])
        assert selected == {"timezone"}

    def test_environment_subset(self, plugin) -> None:
        """Test environment is a valid subset."""
        selected = plugin._resolve_subsets(["environment"])
        assert selected == {"environment"}


class TestMergeFacts:
    """Tests for _merge_facts helper."""

    def test_merge_new_namespace(self, plugin) -> None:
        """Test merging into empty accumulator."""
        acc = {}
        plugin._merge_facts(
            acc,
            {"o0_os": {"kernel": {"name": "linux"}}},
        )
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


class TestBatchedExecution:
    """Tests for the batched COMMAND_SPEC path."""

    def test_environment_in_batched(self, plugin) -> None:
        """Test environment is a batched subset."""
        assert "environment" in plugin.BATCHED_SUBSETS

    def test_locale_derived_from_env(self, plugin) -> None:
        """Test locale is not a separate subset."""
        assert "locale" not in plugin.BATCHED_SUBSETS
        assert "locale" not in plugin.LEGACY_METHODS

    def test_timezone_in_batched_system_scoped(self, plugin) -> None:
        """Test timezone is batched and system-scoped."""
        assert "timezone" in plugin.BATCHED_SUBSETS
        assert "timezone" not in plugin.USER_SCOPED_SUBSETS

    def test_run_environment_keys_by_uid(self, monkeypatch, plugin) -> None:
        """Test environment results keyed under the effective uid
        with locale derived from LANG."""
        plugin._task.args = {"gather_subset": ["!all", "environment"]}
        _mock_effective_uid(monkeypatch, 1000)

        def mock_run(commands, **kwargs):
            return []

        monkeypatch.setattr(plugin, "_run", mock_run)

        def mock_processor(results):
            return (
                {
                    "HOME": "/home/testuser",
                    "LANG": "en_US.UTF-8",
                },
                [],
            )

        monkeypatch.setitem(
            plugin.BATCHED_SUBSETS["environment"],
            "processor",
            mock_processor,
        )

        result = plugin.run(tmp=None, task_vars={})

        user_facts = result["ansible_facts"]["o0_users"]["1000"]
        assert user_facts["uid"] == 1000
        assert user_facts["environment"]["HOME"] == ("/home/testuser")
        assert user_facts["environment"]["LANG"] == ("en_US.UTF-8")
        assert user_facts["locale"] == "en_US.UTF-8"

    def test_environment_dropped_without_uid(
        self, monkeypatch, plugin
    ) -> None:
        """Test environment facts are dropped when id -u did not
        answer, since the canonical key is the uid."""
        plugin._task.args = {"gather_subset": ["!all", "environment"]}
        _mock_effective_uid(monkeypatch, None)

        monkeypatch.setattr(plugin, "_run", lambda commands, **kwargs: [])
        monkeypatch.setitem(
            plugin.BATCHED_SUBSETS["environment"],
            "processor",
            lambda results: ({"LANG": "C"}, []),
        )

        result = plugin.run(tmp=None, task_vars={})

        assert result["ansible_facts"] == {}

    def test_locale_defaults_to_ascii(self, monkeypatch, plugin) -> None:
        """Test locale falls back to ASCII when LANG/LC_ALL
        unset."""
        plugin._task.args = {"gather_subset": ["!all", "environment"]}
        _mock_effective_uid(monkeypatch, 1000)

        def mock_run(commands, **kwargs):
            return []

        monkeypatch.setattr(plugin, "_run", mock_run)

        def mock_processor(results):
            return ({"HOME": "/home/testuser"}, [])

        monkeypatch.setitem(
            plugin.BATCHED_SUBSETS["environment"],
            "processor",
            mock_processor,
        )

        result = plugin.run(tmp=None, task_vars={})

        user_facts = result["ansible_facts"]["o0_users"]["1000"]
        assert user_facts["locale"] == "ASCII"

    def test_locale_c_becomes_ascii(self, monkeypatch, plugin) -> None:
        """Test C locale is translated to ASCII."""
        plugin._task.args = {"gather_subset": ["!all", "environment"]}
        _mock_effective_uid(monkeypatch, 0)

        def mock_run(commands, **kwargs):
            return []

        monkeypatch.setattr(plugin, "_run", mock_run)

        def mock_processor(results):
            return ({"LANG": "C"}, [])

        monkeypatch.setitem(
            plugin.BATCHED_SUBSETS["environment"],
            "processor",
            mock_processor,
        )

        result = plugin.run(tmp=None, task_vars={})

        user_facts = result["ansible_facts"]["o0_users"]["0"]
        assert user_facts["locale"] == "ASCII"


class TestGatherUsers:
    """Tests for the o0_users and o0_groups aggregation."""

    def test_canonical_shape(self, monkeypatch, plugin) -> None:
        """Test the aggregator emits the same shape the users module
        composes."""
        slurped = {
            "/etc/passwd": (
                "root:*:0:0:System Administrator:/var/root:/bin/sh\n"
                "o0-o:*:1000:20:o0-o:/home/o0-o:/bin/zsh"
            ),
            "/etc/group": "wheel:*:0:root\nstaff:*:20:\naccess_bpf:*:101:o0-o",
            "/etc/shells": "/bin/sh\n/bin/zsh",
        }

        def mock_execute(module_name, module_args, task_vars=None):
            return {"stdout": slurped[module_args["src"]]}

        monkeypatch.setattr(plugin, "_execute_module", mock_execute)

        facts = plugin._gather_users(task_vars={})

        assert facts["o0_users"]["1000"] == {
            "name": "o0-o",
            "uid": 1000,
            "gid": 20,
            "gecos": "o0-o",
            "home": "/home/o0-o",
            "shell": "/bin/zsh",
            "groups": [20, 101],
        }
        assert facts["o0_groups"]["101"] == {
            "name": "access_bpf",
            "gid": 101,
            "members": [1000],
        }
        assert facts["o0_shells"] == ["/bin/sh", "/bin/zsh"]

    def test_needs_both_files(self, monkeypatch, plugin) -> None:
        """Test a failed /etc/group read leaves the cross-referenced
        facts unpublished."""

        def mock_execute(module_name, module_args, task_vars=None):
            if module_args["src"] == "/etc/group":
                return {"failed": True}
            return {"stdout": "root:*:0:0:root:/root:/bin/sh"}

        monkeypatch.setattr(plugin, "_execute_module", mock_execute)

        facts = plugin._gather_users(task_vars={})

        assert "o0_users" not in facts
        assert "o0_groups" not in facts


class TestRun:
    """Tests for the full run() method."""

    def test_connection_failure_propagates(self, monkeypatch, plugin) -> None:
        """Test that connection failures are propagated."""
        plugin._task.args = {"gather_subset": ["!all", "fstab"]}

        def mock_execute(module_name, module_args, task_vars=None):
            raise AnsibleConnectionFailure("lost")

        monkeypatch.setattr(plugin, "_execute_module", mock_execute)

        with pytest.raises(AnsibleConnectionFailure):
            plugin.run(tmp=None, task_vars={})

    def test_result_has_invocation(self, plugin) -> None:
        """Test that result includes invocation."""
        plugin._task.args = {"gather_subset": ["!all"]}
        result = plugin.run(tmp=None, task_vars={})
        assert "invocation" in result

    def test_changed_is_false(self, plugin) -> None:
        """Test that changed is always false."""
        plugin._task.args = {"gather_subset": ["!all"]}
        result = plugin.run(tmp=None, task_vars={})
        assert result["changed"] is False

    def test_empty_subset_returns_empty_facts(self, plugin) -> None:
        """Test that !all returns empty ansible_facts."""
        plugin._task.args = {"gather_subset": ["!all"]}
        result = plugin.run(tmp=None, task_vars={})
        assert result["ansible_facts"] == {}
