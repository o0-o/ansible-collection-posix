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

# The files the users and fstab subsets read, as a host answers them
ETC_PASSWD = (
    "root:*:0:0:System Administrator:/var/root:/bin/sh\n"
    "o0-o:*:1000:20:o0-o:/home/o0-o:/bin/zsh"
)
ETC_GROUP = "wheel:*:0:root\nstaff:*:20:\naccess_bpf:*:101:o0-o"
ETC_SHELLS = "# comment\n/bin/sh\n/bin/zsh"
ETC_FSTAB = "/dev/sd0a / ffs rw 1 1"

ETC = {
    "/etc/passwd": ETC_PASSWD,
    "/etc/group": ETC_GROUP,
    "/etc/shells": ETC_SHELLS,
}

# The same host's own resolved view of those users, knowing one the
# files do not
GETENT = {
    "passwd": ETC_PASSWD + "\nldap:*:4000:20:LDAP User:/home/ldap:/bin/sh",
    "group": ETC_GROUP,
}

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
        "o0_os": {"compliance": {"posix": {"supported": True}}},
        "o0_paths": {
            "/bin/sh": {"aliases": {}, "builtins": ["cd", "exec"]},
            "/usr/bin/awk": {
                "executable": True,
                "executable_evidence": "inferred",
            },
        },
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


def _answer_files(
    commands: list[dict[str, Any]],
    files: dict[str, Optional[str]],
) -> list[dict[str, Any]]:
    """Answer the file reads a batch carries, as a host would.

    Every subset hands ``_run`` one list of command requests, the
    ``cat`` of each file a subset reads among them. A file the mapping
    holds answers with its content, and one mapped to None answers as
    a file that is not there.

    :param list[dict[str, Any]] commands: The batch's requests
    :param dict[str, Optional[str]] files: Content per path
    :returns list[dict[str, Any]]: The file requests, answered
    """
    answered = []
    for request in commands:
        if request.get("type") != "file":
            continue
        content = files.get(request["args"]["path"])
        if content is None:
            answered.append(
                {**request, "rc": 1, "stdout": "", "stderr": "no file"}
            )
        else:
            answered.append(
                {**request, "rc": 0, "stdout": content, "stderr": ""}
            )
    return answered


def _answer_getent(
    commands: list[dict[str, Any]],
    getent: Optional[dict[str, str]],
) -> list[dict[str, Any]]:
    """Answer the resolved-view probes a batch carries.

    A host given no ``getent`` answers as one that has no getent at
    all, the way macOS does.

    :param list[dict[str, Any]] commands: The batch's requests
    :param Optional[dict[str, str]] getent: Enumeration per database
    :returns list[dict[str, Any]]: The probe requests, answered
    """
    answered = []
    for request in commands:
        cmd_type = request.get("type", "")
        if not cmd_type.startswith("getent_"):
            continue
        output = (getent or {}).get(cmd_type.split("_", 1)[1])
        if output is None:
            answered.append(
                {
                    **request,
                    "rc": 127,
                    "stdout": "",
                    "stderr": "sh: getent: not found",
                }
            )
        else:
            answered.append(
                {**request, "rc": 0, "stdout": output, "stderr": ""}
            )
    return answered


def _mock_run(
    monkeypatch,
    plugin: ActionModule,
    files: Optional[dict[str, Optional[str]]] = None,
    getent: Optional[dict[str, str]] = None,
) -> None:
    """Answer the one batch the action issues.

    The probes the other subsets contribute go unanswered, because a
    test that wants them patches their processor instead.

    :param monkeypatch: The pytest monkeypatch fixture
    :param ActionModule plugin: Action instance to patch
    :param Optional[dict[str, Optional[str]]] files: Content per path
    :param Optional[dict[str, str]] getent: Enumeration per database,
        or None for a host with no getent
    """
    files = files or {}

    def mock_run(commands, **kwargs) -> Any:
        if not isinstance(commands, list):
            return []
        return _answer_files(commands, files) + _answer_getent(
            commands, getent
        )

    monkeypatch.setattr(plugin, "_run", mock_run)


def _gather(
    plugin: ActionModule,
    subset: str,
    task_vars: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Gather one subset and return the facts it published.

    :param ActionModule plugin: Action instance to run
    :param str subset: The subset to gather
    :param Optional[dict[str, Any]] task_vars: Task variables
    :returns dict[str, Any]: The published ansible_facts
    """
    plugin._task.args = {"gather_subset": [subset]}
    result = plugin.run(tmp=None, task_vars=task_vars or {})
    return result["ansible_facts"]


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

    def test_invalid_negation(self, plugin) -> None:
        """A typo'd exclusion fails like a typo'd selection."""
        with pytest.raises(AnsibleActionFail, match="Invalid gather_subset"):
            plugin._resolve_subsets(["!invalid_subset"])

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
        assert plugin._resolve_subsets(["all"]) == set(plugin.SUBSETS)

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
            assert expanded != set()
            assert expanded <= set(plugin.SUBSETS)

    def test_exclusion_gathers_less_than_all(self, plugin) -> None:
        """Test an exclusion is a strict subset of 'all'. It once
        gathered more, because 'all' dropped a group it named."""
        assert plugin._resolve_subsets(
            ["!dmidecode"]
        ) < plugin._resolve_subsets(["all"])

    def test_negated_group_removes_its_members(self, plugin) -> None:
        """Test negating a group drops the subsets it names."""
        selected = plugin._resolve_subsets(["all", "!storage"])
        assert (plugin.SUBSET_GROUPS["storage"] & selected) == set()
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
        plugin._merge_facts(acc, {"o0_kernel_args": ["quiet", "ro"]})
        assert acc == {"o0_kernel_args": ["quiet", "ro"]}

    def test_merge_list_namespace_beside_dicts(self, plugin) -> None:
        """Test a list namespace lands without disturbing the dict
        namespaces merged alongside it."""
        acc = {"o0_os": {"kernel": {"name": "linux"}}}
        plugin._merge_facts(
            acc,
            {
                "o0_users": {"0": {"uid": 0}},
                "o0_kernel_args": ["quiet"],
            },
        )
        assert acc["o0_os"] == {"kernel": {"name": "linux"}}
        assert acc["o0_users"] == {"0": {"uid": 0}}
        assert acc["o0_kernel_args"] == ["quiet"]

    def test_merge_replaces_a_list_namespace(self, plugin) -> None:
        """Test a dict namespace arriving where a list stands replaces
        it rather than trying to update the list."""
        acc = {"o0_kernel_args": ["quiet"]}
        plugin._merge_facts(acc, {"o0_kernel_args": {"count": 1}})
        assert acc == {"o0_kernel_args": {"count": 1}}

    def test_merge_composes_the_path_store(self, plugin) -> None:
        """Test o0_paths merges through its own composer: a path one
        subset observed stands beside a path another one did, and both
        keep the whole of what was seen."""
        acc = {"o0_paths": {"/bin/sh": {"builtins": ["cd"]}}}
        plugin._merge_facts(
            acc,
            {"o0_paths": {"/etc/shells": {"config": ["/bin/sh"]}}},
        )
        assert acc["o0_paths"] == {
            "/bin/sh": {"builtins": ["cd"]},
            "/etc/shells": {"config": ["/bin/sh"]},
        }

    def test_merge_replaces_a_path_entry_whole(self, plugin) -> None:
        """Test a second observation of a path replaces the first
        rather than blending into it. A mode read before a chmod and a
        size read after it would describe a file that never existed."""
        acc = {"o0_paths": {"/bin/sh": {"mode": "0755", "size": 100}}}
        plugin._merge_facts(acc, {"o0_paths": {"/bin/sh": {"size": 200}}})
        assert acc["o0_paths"]["/bin/sh"] == {"size": 200}

    def test_merge_keeps_a_confirmed_absence(self, plugin) -> None:
        """Test a path observed as absent is published as null, not as
        an entry with nothing in it."""
        acc = {}
        plugin._merge_facts(acc, {"o0_paths": {"/usr/bin/pax": None}})
        assert acc["o0_paths"] == {"/usr/bin/pax": None}

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
        assert "environment" in plugin.SUBSETS

    def test_every_subset_is_batched(self, plugin) -> None:
        """Test one table names every subset, so no subset gathers
        outside the batch. fstab and users were the last two, each
        spending round trips of their own for reads the batch could
        have carried."""
        assert {"fstab", "users"} <= set(plugin.SUBSETS)
        assert all(
            callable(spec["requests"]) and callable(spec["processor"])
            for spec in plugin.SUBSETS.values()
        )
        assert not hasattr(plugin, "LEGACY_METHODS")

    def test_locale_derived_from_env(self, plugin) -> None:
        """Test locale is not a separate subset."""
        assert "locale" not in plugin.SUBSETS

    def test_timezone_in_batched_system_scoped(self, plugin) -> None:
        """Test timezone is batched and system-scoped."""
        assert "timezone" in plugin.SUBSETS
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
            plugin.SUBSETS["environment"],
            "processor",
            mock_processor,
        )

        result = plugin.run(tmp=None, task_vars={})

        user_facts = result["ansible_facts"]["o0_users"]["1000"]
        assert user_facts["uid"] == 1000
        assert user_facts["environment"]["HOME"] == ("/home/testuser")
        assert user_facts["environment"]["LANG"] == ("en_US.UTF-8")
        assert user_facts["locale"] == "en_US.UTF-8"

    def test_id_shape_is_int_under_a_string_key(
        self, monkeypatch, plugin
    ) -> None:
        """Test the identity a gather composes is one shape: the uid
        is an integer field under its own stringified key, with
        nothing flipping between the two forms.

        This one drives the real id -u parse rather than stubbing the
        uid in, so the whole path from what the host printed to what
        is published is pinned.
        """
        plugin._task.args = {"gather_subset": ["!all", "environment"]}

        def mock_run(commands, **kwargs):
            answers = []
            for request in commands:
                if request["type"] == "effective_uid":
                    stdout = "1000"
                else:
                    stdout = {"LANG": "en_US.UTF-8"}.get(
                        request["args"]["env"], ""
                    )
                answers.append(
                    dict(
                        request,
                        rc=0,
                        stdout=stdout,
                        stdout_lines=[stdout],
                        stderr="",
                        stderr_lines=[],
                    )
                )
            return answers

        monkeypatch.setattr(plugin, "_run", mock_run)

        users = plugin.run(tmp=None, task_vars={})["ansible_facts"]["o0_users"]

        assert list(users) == ["1000"]
        assert users["1000"]["uid"] == 1000
        assert isinstance(users["1000"]["uid"], int)
        assert users["1000"]["locale"] == "en_US.UTF-8"

    def test_environment_dropped_without_uid(
        self, monkeypatch, plugin
    ) -> None:
        """Test environment facts are dropped when id -u did not
        answer, since the canonical key is the uid."""
        plugin._task.args = {"gather_subset": ["!all", "environment"]}
        _mock_effective_uid(monkeypatch, None)

        monkeypatch.setattr(plugin, "_run", lambda commands, **kwargs: [])
        monkeypatch.setitem(
            plugin.SUBSETS["environment"],
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
            plugin.SUBSETS["environment"],
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
            plugin.SUBSETS["environment"],
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

        facts = _gather(plugin, "users")

        assert facts["o0_users"]["1000"] == {
            "name": "o0-o",
            "uid": 1000,
            "gid": 20,
            "gecos": "o0-o",
            "home": "/home/o0-o",
            "shell": "/bin/zsh",
            "groups": [20, 101],
            "evidence": {"files": ["/etc/passwd"], "commands": []},
        }
        assert facts["o0_groups"]["101"] == {
            "name": "access_bpf",
            "gid": 101,
            "members": [1000],
            "evidence": {"files": ["/etc/group"], "commands": []},
        }
        assert facts["o0_paths"]["/etc/shells"]["config"] == [
            "/bin/sh",
            "/bin/zsh",
        ]

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

        facts = _gather(plugin, "users")

        assert set(facts) == {
            "o0_users",
            "o0_groups",
            "o0_paths",
            "o0_shell_files",
            "o0_shells",
        }
        # A home is a path, so it is an entry of the path store rather
        # than a namespace of its own, and it accumulates there beside
        # the shells file rather than replacing it
        assert facts["o0_paths"]["/home/o0-o"]["residents"] == [1000]
        assert facts["o0_paths"]["/var/root"]["residents"] == [0]
        assert facts["o0_paths"]["/home/o0-o"]["tags"] == ["posix", "home"]
        assert facts["o0_paths"]["/etc/shells"]["config"] == [
            "/bin/sh",
            "/bin/zsh",
        ]
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

        facts = _gather(
            plugin,
            "users",
            task_vars={"o0_shell_files": {"/bin/ksh": {"type": "regular"}}},
        )

        assert set(facts["o0_shell_files"]) == {
            "/bin/ksh",
            "/bin/sh",
            "/bin/zsh",
        }

    def test_one_round_trip(self, monkeypatch, plugin) -> None:
        """Test all three files are read in a single batch, the one
        batch the gather issues rather than a batch of its own, and
        that asking the host for its own resolved view of the users
        costs no round trip beyond it."""
        _no_python(monkeypatch, plugin)
        _mock_read(monkeypatch, plugin)
        batches = []

        def mock_run(commands, **kwargs):
            batches.append(commands)
            return _answer_files(commands, {})

        monkeypatch.setattr(plugin, "_run", mock_run)

        _gather(plugin, "users")

        assert [request["command"] for request in batches[0]] == [
            ("cat", "/etc/passwd"),
            ("cat", "/etc/group"),
            ("cat", "/etc/shells"),
            ("getent", "passwd"),
            ("getent", "group"),
        ]

        # One batch reads the files. The shells the subset publishes
        # are run rather than read, and running one is asked at a path
        # the first batch had to answer with, so it is the second
        # batch and never part of the first.
        assert len(batches) == 2
        assert [request["type"] for request in batches[1]] == [
            "shell_config"
        ]

    def test_a_host_without_getent_gathers_from_its_files(
        self, monkeypatch, plugin
    ) -> None:
        """Test the absent branch is a gather, not a failure.

        macOS has no getent and posix will not learn Directory
        Services, so the probe finds nothing there and the files-only
        facts are published, saying so.
        """
        _no_python(monkeypatch, plugin)
        _mock_read(monkeypatch, plugin)

        def mock_run(commands, **kwargs):
            answered = _answer_files(commands, ETC)
            answered.extend(
                {
                    **request,
                    "rc": 127,
                    "stdout": "",
                    "stderr": "sh: getent: not found",
                }
                for request in commands
                if request.get("type", "").startswith("getent_")
            )
            return answered

        monkeypatch.setattr(plugin, "_run", mock_run)

        facts = _gather(plugin, "users")

        assert facts["o0_users"]["1000"]["evidence"] == {
            "files": ["/etc/passwd"],
            "commands": [],
        }
        assert facts["o0_groups"]["101"]["evidence"] == {
            "files": ["/etc/group"],
            "commands": [],
        }
        plugin._display.warning.assert_not_called()

    def test_a_resolved_view_overlays_and_says_so(
        self, monkeypatch, plugin
    ) -> None:
        """Test a host whose getent knows more than its files."""
        _no_python(monkeypatch, plugin)
        _mock_read(monkeypatch, plugin)
        _mock_run(monkeypatch, plugin, ETC, getent=GETENT)

        facts = _gather(plugin, "users")

        assert facts["o0_users"]["1000"]["evidence"] == {
            "files": ["/etc/passwd"],
            "commands": ["getent"],
        }
        assert facts["o0_users"]["4000"]["name"] == "ldap"
        assert facts["o0_users"]["4000"]["evidence"] == {
            "files": [],
            "commands": ["getent"],
        }

    def test_both_producers_compose_one_shape(
        self, monkeypatch, plugin
    ) -> None:
        """Test a gather and the users module answer identically.

        One composition builds both, so the same host answers give the
        same o0_users and o0_groups either way - the resolved view and
        its provenance included, which is the whole point of the
        overlay living in the composition rather than in a producer.
        """
        from ansible_collections.o0_o.posix.plugins.module_utils import (
            compose_users_groups,
        )

        _no_python(monkeypatch, plugin)
        _mock_read(monkeypatch, plugin)
        _mock_run(monkeypatch, plugin, ETC, getent=GETENT)

        gathered = _gather(plugin, "users")

        users, groups = compose_users_groups(
            ETC_PASSWD, ETC_GROUP, GETENT["passwd"], GETENT["group"]
        )

        assert gathered["o0_users"] == users
        assert gathered["o0_groups"] == groups

    def test_one_metadata_read(self, monkeypatch, plugin) -> None:
        """Test the homes and the shell files are read together, in
        one metadata read over the deduplicated paths."""
        _no_python(monkeypatch, plugin)
        asked: list[list[str]] = []

        def mock_read(paths, **kwargs) -> dict[str, Any]:
            if isinstance(paths, str):
                paths = [paths]
            asked.append(list(paths))
            return {
                "paths": {
                    path: {"type": READ_TYPES.get(path, "directory")}
                    for path in paths
                }
            }

        monkeypatch.setattr(plugin, "_read", mock_read)
        _mock_run(
            monkeypatch,
            plugin,
            {
                "/etc/passwd": ETC_PASSWD,
                "/etc/group": ETC_GROUP,
                "/etc/shells": ETC_SHELLS,
            },
        )

        facts = _gather(plugin, "users")

        assert asked == [["/bin/sh", "/bin/zsh", "/home/o0-o", "/var/root"]]
        assert facts["o0_paths"]["/home/o0-o"]["residents"] == [1000]
        assert facts["o0_shell_files"]["/bin/zsh"]["tags"] == [
            "posix",
            "shell",
        ]

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

        facts = _gather(plugin, "users")

        assert "o0_users" not in facts
        assert "o0_groups" not in facts
        assert facts["o0_paths"]["/etc/shells"]["config"] == [
            "/bin/sh",
            "/bin/zsh",
        ]

    def test_shells_file_lands_at_its_own_path(
        self, monkeypatch, plugin
    ) -> None:
        """Test the bytes read from a file and the meaning parsed out
        of them are two fields of the one path the file is: raw under
        content, parsed under config."""
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

        facts = _gather(plugin, "users")

        assert facts["o0_paths"]["/etc/shells"] == {
            "content": ETC_SHELLS,
            "config": ["/bin/sh", "/bin/zsh"],
        }

    def test_missing_shells_file(self, monkeypatch, plugin) -> None:
        """Test an unreadable /etc/shells leaves the path unmentioned
        rather than filed as a file that names no shells, which is a
        different answer."""
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

        facts = _gather(plugin, "users")

        # The homes the same gather read are still in the store; the
        # file it could not read is the one path missing from it
        assert "/etc/shells" not in facts["o0_paths"]
        assert facts["o0_paths"]["/home/o0-o"]["tags"] == ["posix", "home"]
        assert facts["o0_users"]["1000"]["shell"] == "/bin/zsh"


class TestGatherFstab:
    """Tests for the /etc/fstab configuration fact."""

    def test_parsed_at_the_path_of_the_file(self, monkeypatch, plugin) -> None:
        """Test what a file configures is a fact about that file: the
        bytes under content and the filesystems they name under
        config, at the file's own key in the flat path store, the way
        /etc/shells lands the login shells it names."""
        _no_python(monkeypatch, plugin)
        _mock_run(monkeypatch, plugin, {"/etc/fstab": ETC_FSTAB})

        facts = _gather(plugin, "fstab")

        entry = facts["o0_paths"]["/etc/fstab"]
        assert entry["content"] == ETC_FSTAB
        assert entry["config"][0]["mount"] == "/"
        assert entry["config"][0]["type"] == "ffs"

    def test_live_state_keeps_its_own_namespace(
        self, monkeypatch, plugin
    ) -> None:
        """Test the fstab subset writes nothing under o0_storage,
        which holds what is mounted now rather than what the host is
        configured to mount."""
        _no_python(monkeypatch, plugin)
        _mock_run(monkeypatch, plugin, {"/etc/fstab": ETC_FSTAB})

        facts = _gather(plugin, "fstab")

        assert set(facts) == {"o0_paths"}
        assert set(facts["o0_paths"]) == {"/etc/fstab"}

    def test_absent_file_publishes_nothing(self, monkeypatch, plugin) -> None:
        """Test a host without /etc/fstab leaves the path out of the
        store rather than filing a null there, which is the store's
        word for a path confirmed absent - and a cat that failed does
        not tell an absent file from an unreadable one."""
        _no_python(monkeypatch, plugin)
        _mock_run(monkeypatch, plugin, {"/etc/fstab": None})

        assert _gather(plugin, "fstab") == {}


class TestDefaultGather:
    """Tests for a default gather driven by every producer's shape."""

    @pytest.fixture
    def gathered(self, monkeypatch, plugin) -> dict[str, Any]:
        """Run a default gather with every real producer's shape.

        The probing subsets' processors answer with the facts they
        really emit, and the two that read files read fabricated ones
        out of the same batch, so the merge that publishes them runs
        exactly as it does on a host.

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
                plugin.SUBSETS[subset],
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
        assert gathered != {}
        assert all(ns.startswith("o0_") for ns in gathered)

    def test_every_subset_lands(self, gathered) -> None:
        """Test a default gather publishes something from each of the
        eight subsets."""
        assert gathered["o0_os"]["kernel"]["name"] == "darwin"
        assert gathered["o0_os"]["timezone"]["abbreviation"] == "EDT"
        assert gathered["o0_os"]["compliance"]["posix"]["supported"] is True
        assert gathered["o0_hardware"]["baseboard"]["make"] == "Apple Inc."
        assert gathered["o0_storage"]["mounts"]["/"]["type"] == "apfs"
        assert gathered["o0_paths"]["/etc/fstab"]["config"][0]["type"] == (
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

    def test_shells_are_the_config_of_the_file_that_names_them(
        self, gathered
    ) -> None:
        """Test the login shells a host names are the parsed meaning of
        the one file they are named in, filed at that file's path."""
        assert gathered["o0_paths"]["/etc/shells"]["config"] == [
            "/bin/sh",
            "/bin/zsh",
        ]

    def test_three_subsets_share_one_path_store(self, gathered) -> None:
        """Test the compliance sweep, the users read and the fstab
        read compose into one store rather than each replacing the
        others' paths."""
        paths = gathered["o0_paths"]
        assert paths["/bin/sh"]["builtins"] == ["cd", "exec"]
        assert paths["/usr/bin/awk"]["executable"] is True
        assert paths["/etc/shells"]["content"] == ETC_SHELLS
        assert paths["/etc/fstab"]["content"] == ETC_FSTAB
        assert paths["/home/o0-o"]["tags"] == ["posix", "home"]

    def test_the_retired_namespaces_are_gone(self, gathered) -> None:
        """Test the namespaces the path store absorbed are not
        published beside it. A second copy of an answer is a copy that
        can drift from the first."""
        assert "o0_missing" not in gathered
        assert "shells" not in gathered["o0_os"]
        # o0_shells is not one of them. It went away as a list of the
        # login shells a host names and came back as a store keyed by
        # shell path, which is where what running one produces is
        # filed. The names it holds are the same names.
        assert set(gathered["o0_shells"]) == set(
            gathered["o0_paths"]["/etc/shells"]["config"]
        )
        # What the host is configured to mount is a fact about the
        # file that configures it; o0_storage holds live state, and
        # says beside it what was consulted to learn it
        assert set(gathered["o0_storage"]) == {"mounts", "evidence"}

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

        monkeypatch.setattr(
            module,
            "_run",
            lambda commands, **kwargs: _answer_files(commands, self.ETC_FILES),
        )
        _mock_read(monkeypatch, module)

        return module.run(task_vars={})

    def test_both_publish_one_set_of_facts(
        self, monkeypatch, plugin, standalone
    ) -> None:
        """Test every user fact means the same thing from either
        producer. The gather used to publish three of the four and the
        module the other three, disagreeing on which names existed.
        """
        _no_python(monkeypatch, plugin)
        _mock_read(monkeypatch, plugin)
        _mock_run(monkeypatch, plugin, self.ETC_FILES)

        gathered = _gather(plugin, "users")

        assert set(gathered) == {
            "o0_users",
            "o0_groups",
            "o0_paths",
            "o0_shell_files",
            "o0_shells",
        }
        for fact, value in gathered.items():
            assert value == standalone[fact], fact


def test_no_action_plugin_reads_the_raw_identity_utils() -> None:
    """Test every producer of a user fact routes through the shared
    composition.

    passwd_info, group_info and id_info answer with the shapes their
    filters publish: a name-keyed id field, membership counted in
    names, fields that flip between numeric and named form. Those
    shapes are those filters' API and stay as they are; what keeps
    them out of a fact is that no plugin publishing one reads them
    directly.
    """
    import re
    from pathlib import Path

    from ansible_collections.o0_o.posix.plugins import action as action_pkg

    # An Ansible plugin directory carries no __init__, so the package
    # is a namespace package and has no __file__ to take a parent of.
    # The guard read that None and raised, which is a guard that never
    # once looked at an action plugin.
    directories = [Path(entry) for entry in action_pkg.__path__]
    assert directories != []

    raw = re.compile(r"\b(passwd_info|group_info|id_info)\b")

    offenders = sorted(
        path.name
        for directory in directories
        for path in directory.glob("*.py")
        if raw.search(path.read_text())
    )

    assert offenders == []
