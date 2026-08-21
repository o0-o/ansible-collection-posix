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

from typing import Any, Generator, Optional

import pytest

from ansible.errors import AnsibleActionFail, AnsibleConnectionFailure
from ansible_collections.o0_o.posix.plugins.action.facts import (
    ActionModule,
)
from ansible_collections.o0_o.posix.plugins.action.users import (
    ActionModule as UsersActionModule,
)

# The files the legacy subsets read, as a host answers them
ETC_PASSWD = (
    "root:*:0:0:System Administrator:/var/root:/bin/sh\n"
    "o0-o:*:1000:20:o0-o:/home/o0-o:/bin/zsh"
)
ETC_GROUP = "wheel:*:0:root\nstaff:*:20:\naccess_bpf:*:101:o0-o"
ETC_SHELLS = "# comment\n/bin/sh\n/bin/zsh"
ETC_FSTAB = "/dev/sd0a / ffs rw 1 1"

# What the read action answers for the paths those files name
READ_TYPES = {
    "/var/root": "directory",
    "/home/o0-o": "directory",
    "/bin/sh": "regular",
    "/bin/zsh": "regular",
}

# What each batched subset's processor really emits, trimmed to one
# entry per namespace. Captured from a default gather on a live host.
PRODUCER_FACTS = {
    "uname": {
        "o0_os": {
            "kernel": {
                "pretty": "Darwin",
                "name": "darwin",
                "version": {"id": "25.5.0"},
            },
        },
        "o0_network": {"hostname": {"short": "host"}},
        "o0_hardware": {"baseboard": {"architecture": "arm64"}},
    },
    "timezone": {
        "o0_os": {
            "timezone": {"abbreviation": "EDT", "offset": "-0400"},
        },
    },
    "dmidecode": {
        "o0_hardware": {"baseboard": {"make": "Apple Inc."}},
    },
    "mounts": {
        "o0_storage": {
            "mounts": {
                "/": {
                    "source": {"path": "/dev/disk3s1s1"},
                    "capacity": {
                        "total": {
                            "bytes": 494384795648,
                            "pretty": "460.43 GiB",
                        },
                        "used": {
                            "bytes": 10485760000,
                            "pretty": "9.77 GiB",
                            "percent": 2.12,
                        },
                    },
                    "type": "apfs",
                    "options": {"local": True, "read-only": True},
                },
            },
        },
    },
    "compliance": {
        "o0_os": {
            "compliance": {"posix": {"supported": True}},
            "shells": {
                "/bin/sh": {"aliases": {}, "builtins": ["cd", "exec"]},
            },
        },
        "o0_paths": {"/bin/sh": {}},
        "o0_missing": {"commands": []},
    },
    # The environment processor answers with the raw variables; run()
    # is what keys them under the effective uid.
    "environment": {"HOME": "/var/root", "LANG": "en_US.UTF-8"},
}


def _mock_effective_uid(monkeypatch, uid) -> None:
    """Answer the batched ``id -u`` with a fixed uid."""
    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.action.facts."
        "process_effective_uid_results",
        lambda results: uid,
    )


def _mock_run(
    monkeypatch,
    plugin: ActionModule,
    files: Optional[dict[str, Optional[str]]] = None,
) -> None:
    """Answer both shapes of ``_run`` the action issues.

    The batched subsets hand ``_run`` a list of command requests and
    read their results through their processors; the legacy subsets
    hand it a mapping of path to ``cat``, so the mapping answers with
    file content and a path mapped to None answers as unreadable.

    :param monkeypatch: The pytest monkeypatch fixture
    :param ActionModule plugin: Action instance to patch
    :param Optional[dict[str, Optional[str]]] files: Content per path
    """
    files = files or {}

    def mock_run(commands, **kwargs) -> Any:
        if not isinstance(commands, dict):
            return []
        answers = {}
        for path in commands:
            content = files.get(path)
            if content is None:
                answers[path] = {"rc": 1, "stdout": "", "stderr": "no file"}
            else:
                answers[path] = {"rc": 0, "stdout": content}
        return answers

    monkeypatch.setattr(plugin, "_run", mock_run)


def _mock_read(monkeypatch, plugin: Any) -> None:
    """Answer the read action with the type each path really is.

    The home and shell-file facts are metadata the read action
    gathers, and read has its own tests; answering with the type is
    enough for the compositions that key on it to run for real.

    :param monkeypatch: The pytest monkeypatch fixture
    :param Any plugin: Action instance to patch
    """

    def mock_read(paths, **kwargs) -> dict[str, Any]:
        if isinstance(paths, str):
            paths = [paths]
        return {
            "paths": {
                path: {"type": READ_TYPES.get(path, "directory")}
                for path in paths
            }
        }

    monkeypatch.setattr(plugin, "_read", mock_read)


def _no_python(monkeypatch, plugin: ActionModule) -> None:
    """Fail the test if the action reaches for a Python module.

    The module gathers facts from hosts without Python, so nothing it
    does may route through _execute_module — slurp included.

    :param monkeypatch: The pytest monkeypatch fixture
    :param ActionModule plugin: Action instance to patch
    """

    def no_execute_module(*args, **kwargs) -> None:
        raise AssertionError("facts ran a Python module on the managed host")

    monkeypatch.setattr(plugin, "_execute_module", no_execute_module)


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

    def test_all_is_every_subset(self, plugin) -> None:
        """Test 'all' resolves to every subset there is, which it can
        only do by expanding the groups it names."""
        assert plugin._resolve_subsets(["all"]) == set(plugin.SUBSET_METHODS)

    def test_all_contains_the_storage_group(self, plugin) -> None:
        """Test the members of a group named inside 'all' are
        selected, not the group name."""
        selected = plugin._resolve_subsets(["all"])
        assert plugin.SUBSET_GROUPS["storage"] <= selected
        assert "storage" not in selected

    def test_every_group_expands_to_subsets(self, plugin) -> None:
        """Test no group leaves a group name behind, so a member can
        never be silently dropped."""
        for group in plugin.SUBSET_GROUPS:
            expanded = plugin._expand_group(group)
            assert expanded
            assert expanded <= set(plugin.SUBSET_METHODS)

    def test_exclusion_gathers_less_than_all(self, plugin) -> None:
        """Test an exclusion is a strict subset of 'all'. It once
        gathered more, because 'all' dropped a group it named."""
        assert plugin._resolve_subsets(
            ["!dmidecode"]
        ) < plugin._resolve_subsets(["all"])

    def test_negated_group_removes_its_members(self, plugin) -> None:
        """Test negating a group drops the subsets it names."""
        selected = plugin._resolve_subsets(["all", "!storage"])
        assert not plugin.SUBSET_GROUPS["storage"] & selected
        assert "uname" in selected

    def test_group_cycle_terminates(self, monkeypatch, plugin) -> None:
        """Test a group that names itself through another group is
        expanded once."""
        monkeypatch.setitem(plugin.SUBSET_GROUPS, "loop", {"twist", "uname"})
        monkeypatch.setitem(plugin.SUBSET_GROUPS, "twist", {"loop", "fstab"})
        assert plugin._resolve_subsets(["loop"]) == {"uname", "fstab"}

    def test_group_naming_a_stranger_fails(self, monkeypatch, plugin) -> None:
        """Test a group naming neither a subset nor a group says so
        rather than gathering nothing."""
        monkeypatch.setitem(plugin.SUBSET_GROUPS, "loop", {"nonesuch"})
        with pytest.raises(
            AnsibleActionFail, match="neither a subset nor a group"
        ):
            plugin._resolve_subsets(["loop"])


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

    def test_merge_list_namespace(self, plugin) -> None:
        """Test a namespace holding a list is published whole. It once
        cost the whole payload: iterating it raised, and the caller
        turned the exception into a warning."""
        acc = {}
        plugin._merge_facts(acc, {"o0_shells": ["/bin/sh", "/bin/zsh"]})
        assert acc == {"o0_shells": ["/bin/sh", "/bin/zsh"]}

    def test_merge_list_namespace_beside_dicts(self, plugin) -> None:
        """Test a list namespace lands without disturbing the dict
        namespaces merged alongside it."""
        acc = {"o0_os": {"kernel": {"name": "linux"}}}
        plugin._merge_facts(
            acc,
            {
                "o0_users": {"0": {"uid": 0}},
                "o0_shells": ["/bin/sh"],
            },
        )
        assert acc["o0_os"] == {"kernel": {"name": "linux"}}
        assert acc["o0_users"] == {"0": {"uid": 0}}
        assert acc["o0_shells"] == ["/bin/sh"]

    def test_merge_replaces_a_list_namespace(self, plugin) -> None:
        """Test a dict namespace arriving where a list stands replaces
        it rather than trying to update the list."""
        acc = {"o0_shells": ["/bin/sh"]}
        plugin._merge_facts(acc, {"o0_shells": {"count": 1}})
        assert acc == {"o0_shells": {"count": 1}}

    def test_merge_keeps_a_list_value(self, plugin) -> None:
        """Test a list inside a namespace is a value like any other."""
        acc = {"o0_storage": {"config": {}}}
        plugin._merge_facts(
            acc,
            {"o0_storage": {"mounts": [{"mount": "/"}]}},
        )
        assert acc["o0_storage"]["mounts"] == [{"mount": "/"}]
        assert acc["o0_storage"]["config"] == {}


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
        _no_python(monkeypatch, plugin)
        _mock_read(monkeypatch, plugin)
        _mock_run(
            monkeypatch,
            plugin,
            {
                "/etc/passwd": ETC_PASSWD,
                "/etc/group": ETC_GROUP,
                "/etc/shells": ETC_SHELLS,
            },
        )

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

    def test_publishes_every_user_fact(self, monkeypatch, plugin) -> None:
        """Test the subset publishes the whole set the users module
        returns, not the three of five it used to."""
        _no_python(monkeypatch, plugin)
        _mock_read(monkeypatch, plugin)
        _mock_run(
            monkeypatch,
            plugin,
            {
                "/etc/passwd": ETC_PASSWD,
                "/etc/group": ETC_GROUP,
                "/etc/shells": ETC_SHELLS,
            },
        )

        facts = plugin._gather_users(task_vars={})

        assert set(facts) == {
            "o0_users",
            "o0_groups",
            "o0_shells",
            "o0_homes",
            "o0_shell_files",
        }
        assert facts["o0_homes"]["/home/o0-o"]["residents"] == [1000]
        assert facts["o0_homes"]["/var/root"]["residents"] == [0]
        assert facts["o0_shell_files"]["/bin/zsh"]["tags"] == [
            "posix",
            "shell",
        ]

    def test_shell_files_extend_a_prior_gather(
        self, monkeypatch, plugin
    ) -> None:
        """Test the accumulate-across-calls loop closes now that the
        fact it seeds from is a fact the gather publishes."""
        _no_python(monkeypatch, plugin)
        _mock_read(monkeypatch, plugin)
        _mock_run(
            monkeypatch,
            plugin,
            {
                "/etc/passwd": ETC_PASSWD,
                "/etc/group": ETC_GROUP,
                "/etc/shells": ETC_SHELLS,
            },
        )

        facts = plugin._gather_users(
            task_vars={"o0_shell_files": {"/bin/ksh": {"type": "regular"}}}
        )

        assert set(facts["o0_shell_files"]) == {
            "/bin/ksh",
            "/bin/sh",
            "/bin/zsh",
        }

    def test_one_round_trip(self, monkeypatch, plugin) -> None:
        """Test all three files are read in a single batch."""
        _no_python(monkeypatch, plugin)
        _mock_read(monkeypatch, plugin)
        batches = []

        def mock_run(commands, **kwargs):
            batches.append(commands)
            return {path: {"rc": 0, "stdout": ""} for path in commands}

        monkeypatch.setattr(plugin, "_run", mock_run)

        plugin._gather_users(task_vars={})

        assert len(batches) == 1
        assert set(batches[0]) == {
            "/etc/passwd",
            "/etc/group",
            "/etc/shells",
        }
        assert batches[0]["/etc/passwd"] == ["cat", "/etc/passwd"]

    def test_needs_both_files(self, monkeypatch, plugin) -> None:
        """Test a failed /etc/group read leaves the cross-referenced
        facts unpublished."""
        _no_python(monkeypatch, plugin)
        _mock_read(monkeypatch, plugin)
        _mock_run(
            monkeypatch,
            plugin,
            {
                "/etc/passwd": ETC_PASSWD,
                "/etc/group": None,
                "/etc/shells": ETC_SHELLS,
            },
        )

        facts = plugin._gather_users(task_vars={})

        assert "o0_users" not in facts
        assert "o0_groups" not in facts
        assert facts["o0_shells"] == ["/bin/sh", "/bin/zsh"]

    def test_missing_shells_file(self, monkeypatch, plugin) -> None:
        """Test an unreadable /etc/shells leaves o0_shells absent
        rather than empty, since an empty list reads as a host with no
        login shells."""
        _no_python(monkeypatch, plugin)
        _mock_read(monkeypatch, plugin)
        _mock_run(
            monkeypatch,
            plugin,
            {
                "/etc/passwd": ETC_PASSWD,
                "/etc/group": ETC_GROUP,
                "/etc/shells": None,
            },
        )

        facts = plugin._gather_users(task_vars={})

        assert "o0_shells" not in facts
        assert facts["o0_users"]["1000"]["shell"] == "/bin/zsh"


class TestGatherFstab:
    """Tests for the /etc/fstab configuration fact."""

    def test_parsed_under_storage_config(self, monkeypatch, plugin) -> None:
        """Test fstab lands under o0_storage.config keyed by path."""
        _no_python(monkeypatch, plugin)
        _mock_run(monkeypatch, plugin, {"/etc/fstab": ETC_FSTAB})

        facts = plugin._gather_fstab(task_vars={})

        entries = facts["o0_storage"]["config"]["/etc/fstab"]
        assert entries[0]["mount"] == "/"
        assert entries[0]["type"] == "ffs"

    def test_absent_file_publishes_nothing(self, monkeypatch, plugin) -> None:
        """Test a host without /etc/fstab publishes no config fact."""
        _no_python(monkeypatch, plugin)
        _mock_run(monkeypatch, plugin, {"/etc/fstab": None})

        assert plugin._gather_fstab(task_vars={}) == {}


class TestDefaultGather:
    """Tests for a default gather driven by every producer's shape."""

    @pytest.fixture
    def gathered(self, monkeypatch, plugin) -> dict[str, Any]:
        """Run a default gather with every real producer's shape.

        Each batched processor answers with the facts that subset
        really emits and the legacy pair reads fabricated files, so
        the merge that publishes them runs exactly as it does on a
        host.

        :returns dict[str, Any]: The published ansible_facts
        """
        plugin._task.args = {}
        _no_python(monkeypatch, plugin)
        _mock_read(monkeypatch, plugin)
        _mock_effective_uid(monkeypatch, 0)
        _mock_run(
            monkeypatch,
            plugin,
            {
                "/etc/passwd": ETC_PASSWD,
                "/etc/group": ETC_GROUP,
                "/etc/shells": ETC_SHELLS,
                "/etc/fstab": ETC_FSTAB,
            },
        )

        for subset, facts in PRODUCER_FACTS.items():
            monkeypatch.setitem(
                plugin.BATCHED_SUBSETS[subset],
                "processor",
                lambda results, facts=facts: (facts, []),
            )

        result = plugin.run(tmp=None, task_vars={})
        plugin._display.warning.assert_not_called()
        return result["ansible_facts"]

    def test_every_namespace_is_prefixed(self, gathered) -> None:
        """Test every published namespace takes the o0_ prefix. Two
        producers used to publish bare names straight into the
        facts."""
        assert gathered
        assert all(ns.startswith("o0_") for ns in gathered)

    def test_every_subset_lands(self, gathered) -> None:
        """Test a default gather publishes something from each of the
        eight subsets."""
        assert gathered["o0_os"]["kernel"]["name"] == "darwin"
        assert gathered["o0_os"]["timezone"]["abbreviation"] == "EDT"
        assert gathered["o0_os"]["compliance"]["posix"]["supported"] is True
        assert gathered["o0_hardware"]["baseboard"]["make"] == "Apple Inc."
        assert gathered["o0_storage"]["mounts"]["/"]["type"] == "apfs"
        assert gathered["o0_storage"]["config"]["/etc/fstab"][0]["type"] == (
            "ffs"
        )
        assert gathered["o0_users"]["1000"]["name"] == "o0-o"
        assert gathered["o0_users"]["0"]["environment"]["LANG"] == (
            "en_US.UTF-8"
        )

    def test_mounts_are_keyed_and_carry_capacity(self, gathered) -> None:
        """Test the gathered mounts fact is the shape the mounts
        module returns: keyed by mount point, capacity included."""
        mounts = gathered["o0_storage"]["mounts"]
        assert list(mounts) == ["/"]
        assert isinstance(mounts["/"]["capacity"]["total"]["bytes"], int)
        assert "mount" not in mounts["/"]

    def test_shells_is_a_list_of_paths(self, gathered) -> None:
        """Test o0_shells is the list of shells /etc/shells names,
        which is what the users module tells playbooks to read."""
        assert gathered["o0_shells"] == ["/bin/sh", "/bin/zsh"]

    def test_compliance_keeps_its_own_namespaces(self, gathered) -> None:
        """Test the compliance payload lands under the names the
        standalone action publishes."""
        assert gathered["o0_paths"] == {"/bin/sh": {}}
        assert gathered["o0_missing"] == {"commands": []}
        assert "/bin/sh" in gathered["o0_os"]["shells"]

    def test_two_producers_share_one_user(self, gathered) -> None:
        """Test the environment subset and /etc/passwd meet in one
        entry when they answer for the same uid."""
        root = gathered["o0_users"]["0"]
        assert root["name"] == "root"
        assert root["uid"] == 0
        assert root["locale"] == "en_US.UTF-8"


class TestRun:
    """Tests for the full run() method."""

    def test_connection_failure_propagates(self, monkeypatch, plugin) -> None:
        """Test that connection failures are propagated."""
        plugin._task.args = {"gather_subset": ["!all", "fstab"]}

        def mock_run(commands, **kwargs):
            raise AnsibleConnectionFailure("lost")

        monkeypatch.setattr(plugin, "_run", mock_run)

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


class TestUsersProducersAgree:
    """Tests that a gather and the users module answer alike."""

    ETC_FILES = {
        "/etc/passwd": ETC_PASSWD,
        "/etc/group": ETC_GROUP,
        "/etc/shells": ETC_SHELLS,
    }

    @pytest.fixture
    def standalone(self, monkeypatch, base) -> dict[str, Any]:
        """Run the users module against the fabricated host.

        :returns dict[str, Any]: The module's result
        """
        base._task.action = "users"
        base._task.args = {}

        module = UsersActionModule(
            task=base._task,
            connection=base._connection,
            play_context=base._play_context,
            loader=base._loader,
            templar=base._templar,
            shared_loader_obj=base._shared_loader_obj,
        )
        module._display = base._display
        module.inventory_hostname = "localhost"

        def mock_cmd(cmd, task_vars=None, **kwargs):
            if isinstance(cmd, list) and cmd[:1] == ["cat"]:
                content = self.ETC_FILES.get(cmd[1])
                if content is not None:
                    return {"rc": 0, "stdout": content}
            return {"rc": 1}

        monkeypatch.setattr(module, "_command", mock_cmd)
        _mock_read(monkeypatch, module)

        return module.run(task_vars={})

    def test_both_publish_one_set_of_facts(
        self, monkeypatch, plugin, standalone
    ) -> None:
        """Test every user fact means the same thing from either
        producer. The gather used to publish three of the five and the
        module the other four, disagreeing on which names existed.
        """
        _no_python(monkeypatch, plugin)
        _mock_read(monkeypatch, plugin)
        _mock_run(monkeypatch, plugin, self.ETC_FILES)

        gathered = plugin._gather_users(task_vars={})

        assert set(gathered) == {
            "o0_users",
            "o0_groups",
            "o0_shells",
            "o0_homes",
            "o0_shell_files",
        }
        for fact, value in gathered.items():
            assert value == standalone[fact], fact
