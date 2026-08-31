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

"""Unit tests for the sysctl action plugin."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Generator, Optional

import pytest

from ansible.errors import AnsibleActionFail

from ansible_collections.o0_o.posix.plugins.action.sysctl import ActionModule

# An excerpt of a live `sysctl -a` off an Arch host
CORPUS = (
    Path(__file__).parents[1]
    / "module_utils"
    / "files"
    / "sysctl_linux_casa.txt"
)

# What the fabricated host holds, and what it will not let go of
HELD = {
    "kernel.hostname": "casa-hank",
    "vm.swappiness": "60",
    "kernel.sysrq": "16",
}
READ_ONLY = ("kernel.ostype",)


@pytest.fixture
def plugin(base) -> Generator[ActionModule, None, None]:
    """Create an ActionModule instance for sysctl tests."""
    base._task.async_val = False
    base._task.action = "sysctl"
    base._task.args = {}
    # A task is neither of these unless the play says so, and a mock
    # left to itself is truthy for both
    base._task.check_mode = False
    base._task.diff = False

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


def _answer(
    monkeypatch,
    plugin: ActionModule,
    held: Optional[dict[str, str]] = None,
    missing: bool = False,
) -> list[list[dict[str, Any]]]:
    """Answer reads and assignments the way a running host would.

    A key the host does not hold answers non-zero with nothing on
    stdout, which is what a real sysctl does. An assignment to a
    read-only key answers non-zero too, and one to a key the host
    holds takes effect on the fabricated host.

    :param monkeypatch: The pytest monkeypatch fixture
    :param ActionModule plugin: Action instance to patch
    :param Optional[dict[str, str]] held: What the host holds
    :param bool missing: Whether the host has no sysctl at all
    :returns list[list[dict[str, Any]]]: The batches the module issued
    """
    values = dict(HELD if held is None else held)
    batches: list[list[dict[str, Any]]] = []

    def mock_run(commands: Any, **kwargs: Any) -> list[dict[str, Any]]:
        batches.append(commands)
        answered = []
        for request in commands:
            if missing:
                answered.append(
                    {
                        **request,
                        "rc": 127,
                        "stdout": "",
                        "stderr": "sh: sysctl: not found",
                    }
                )
                continue

            kind = request["type"]

            if kind == "sysctl_listing":
                text = CORPUS.read_text()
                answered.append({**request, "rc": 1, "stdout": text})
                continue

            if kind == "sysctl_assign":
                key, _sep, value = request["command"][1].partition("=")
                if key in READ_ONLY:
                    answered.append(
                        {
                            **request,
                            "rc": 1,
                            "stdout": "",
                            "stderr": f"sysctl: setting key {key}",
                        }
                    )
                    continue
                values[key] = value
                answered.append(
                    {**request, "rc": 0, "stdout": f"{key} = {value}\n"}
                )
                continue

            key = request["command"][1]
            if key in values:
                answered.append(
                    {**request, "rc": 0, "stdout": f"{key} = {values[key]}\n"}
                )
            else:
                answered.append(
                    {
                        **request,
                        "rc": 1,
                        "stdout": "",
                        "stderr": f"sysctl: cannot stat {key}",
                    }
                )
        return answered

    monkeypatch.setattr(plugin, "_run", mock_run)
    return batches


def test_a_named_key_answers_verbatim(monkeypatch, plugin) -> None:
    """Test the value is the string the host printed."""
    _answer(monkeypatch, plugin)
    plugin._task.args = {"name": ["kernel.hostname", "vm.swappiness"]}

    result = plugin.run(task_vars={})

    assert result["changed"] is False
    assert result["sysctl"] == {
        "kernel.hostname": "casa-hank",
        "vm.swappiness": "60",
    }


def test_a_key_the_host_refused_is_null(monkeypatch, plugin) -> None:
    """Test a named key gets an answer even when there is none.

    The task named it, so the answer is about that key, and null is
    this collection's word for asked about and not there.
    """
    _answer(monkeypatch, plugin)
    plugin._task.args = {"name": ["kernel.nosuchkey"]}

    result = plugin.run(task_vars={})

    assert result["sysctl"] == {"kernel.nosuchkey": None}


def test_naming_no_key_asks_for_all_of_them(monkeypatch, plugin) -> None:
    """Test the default is the whole listing, in one command."""
    batches = _answer(monkeypatch, plugin)

    result = plugin.run(task_vars={})

    assert [
        request["type"] for batch in batches for request in batch
    ] == ["sysctl_listing"]
    assert result["sysctl"]["kernel.ostype"] == "Linux"
    assert len(result["sysctl"]) > 10


def test_a_value_already_in_force_is_not_set(monkeypatch, plugin) -> None:
    """Test the compare comes first, so a no-op reports no change."""
    batches = _answer(monkeypatch, plugin)
    plugin._task.args = {"values": {"vm.swappiness": "60"}}

    result = plugin.run(task_vars={})

    assert result["changed"] is False
    assert result["sysctl"] == {"vm.swappiness": "60"}
    assert [
        request["type"] for batch in batches for request in batch
    ] == ["sysctl_key"]


def test_a_value_that_differs_is_set(monkeypatch, plugin) -> None:
    """Test the assignment is issued and the answer is read back."""
    batches = _answer(monkeypatch, plugin)
    plugin._task.args = {"values": {"vm.swappiness": "10"}}

    result = plugin.run(task_vars={})

    assert result["changed"] is True
    assert result["sysctl"] == {"vm.swappiness": "10"}

    issued = [request for batch in batches for request in batch]
    assert [request["type"] for request in issued] == [
        "sysctl_key",
        "sysctl_assign",
        "sysctl_key",
    ]
    # Plainly, and never with -w
    assert issued[1]["command"] == ("sysctl", "vm.swappiness=10")


def test_what_comes_back_is_what_the_kernel_says(
    monkeypatch, plugin
) -> None:
    """Test the reported value is read back rather than assumed.

    A kernel that normalized a value on the way in has answered, and
    the task's string was only a request.
    """
    values = dict(HELD)
    batches: list[list[dict[str, Any]]] = []

    def mock_run(commands: Any, **kwargs: Any) -> list[dict[str, Any]]:
        batches.append(commands)
        answered = []
        for request in commands:
            if request["type"] == "sysctl_assign":
                key, _sep, _value = request["command"][1].partition("=")
                # The host takes the value and rewrites it
                values[key] = "10"
                answered.append({**request, "rc": 0, "stdout": ""})
                continue
            key = request["command"][1]
            answered.append(
                {**request, "rc": 0, "stdout": f"{key} = {values[key]}\n"}
            )
        return answered

    monkeypatch.setattr(plugin, "_run", mock_run)
    plugin._task.args = {"values": {"vm.swappiness": "010"}}

    result = plugin.run(task_vars={})

    assert result["changed"] is True
    assert result["sysctl"] == {"vm.swappiness": "10"}


def test_a_refused_assignment_fails_naming_the_key(
    monkeypatch, plugin
) -> None:
    """Test a set that did not happen does not read as success.

    A read-only key and an unprivileged session both refuse, and
    either way the value asked for is not the value in force.
    """
    _answer(monkeypatch, plugin, held={"kernel.ostype": "Linux"})
    plugin._task.args = {"values": {"kernel.ostype": "Darwin"}}

    with pytest.raises(AnsibleActionFail, match="kernel.ostype"):
        plugin.run(task_vars={})


def test_check_mode_reports_the_change_and_makes_none(
    monkeypatch, plugin
) -> None:
    """Test check mode compares and reports without setting."""
    batches = _answer(monkeypatch, plugin)
    plugin._task.args = {"values": {"vm.swappiness": "10"}}
    plugin._task.check_mode = True

    result = plugin.run(task_vars={})

    assert result["changed"] is True
    # What the host says now, because nothing was set
    assert result["sysctl"] == {"vm.swappiness": "60"}
    assert [
        request["type"] for batch in batches for request in batch
    ] == ["sysctl_key"]


def test_a_host_with_no_sysctl_fails_plainly(monkeypatch, plugin) -> None:
    """Test the absence of the tool is named rather than reported empty.

    A POSIX host need not have sysctl, and an explicit inquiry may fail
    loud where a gather would rather report nothing.
    """
    _answer(monkeypatch, plugin, missing=True)
    plugin._task.args = {"name": ["kernel.hostname"]}

    with pytest.raises(AnsibleActionFail, match="no sysctl to ask"):
        plugin.run(task_vars={})


def test_setting_and_reporting_in_one_task(monkeypatch, plugin) -> None:
    """Test a task may set some keys and report others."""
    _answer(monkeypatch, plugin)
    plugin._task.args = {
        "values": {"vm.swappiness": "10"},
        "name": ["kernel.hostname"],
    }

    result = plugin.run(task_vars={})

    assert result["changed"] is True
    assert result["sysctl"] == {
        "kernel.hostname": "casa-hank",
        "vm.swappiness": "10",
    }


def test_the_result_names_the_command_that_answered(
    monkeypatch, plugin
) -> None:
    """Test one command answers every question here."""
    _answer(monkeypatch, plugin)
    plugin._task.args = {"name": ["kernel.hostname"]}

    result = plugin.run(task_vars={})

    assert result["evidence"] == {"commands": ["sysctl"]}


def test_a_diff_names_the_key_it_would_move(monkeypatch, plugin) -> None:
    """Test the diff reads as a before and an after of one key."""
    _answer(monkeypatch, plugin)
    plugin._task.args = {"values": {"vm.swappiness": "10"}}
    plugin._task.check_mode = True
    plugin._task.diff = True

    result = plugin.run(task_vars={})

    assert result["diff"] == [
        {
            "before": {"vm.swappiness": "60"},
            "after": {"vm.swappiness": "10"},
            "before_header": "vm.swappiness",
            "after_header": "vm.swappiness",
        }
    ]


def test_a_task_that_changes_nothing_offers_no_diff(
    monkeypatch, plugin
) -> None:
    """Test a query has nothing to show a difference of."""
    _answer(monkeypatch, plugin)
    plugin._task.args = {"name": ["vm.swappiness"]}
    plugin._task.diff = True

    result = plugin.run(task_vars={})

    assert "diff" not in result


def test_nothing_is_published_as_facts(monkeypatch, plugin) -> None:
    """Test a tunable is not a fact.

    Keys and meanings are the kernel's rather than POSIX's, so nothing
    here is published under a namespace a gather would merge.
    """
    _answer(monkeypatch, plugin)
    plugin._task.args = {"name": ["kernel.hostname"]}

    result = plugin.run(task_vars={})

    assert "ansible_facts" not in result
