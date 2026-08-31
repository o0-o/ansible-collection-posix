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

from typing import Any, Generator

import pytest

from ansible_collections.o0_o.posix.plugins.action.config import ActionModule

# What the fabricated host answers for each variable it is asked
ANSWERS = {
    "ARG_MAX": "1048576",
    "OPEN_MAX": "1024",
    "_POSIX_VERSION": "200809",
    # A variable the host has and does not limit
    "SYMLOOP_MAX": "undefined",
}


@pytest.fixture
def plugin(base) -> Generator[ActionModule, None, None]:
    """Create an ActionModule instance for configuration tests."""
    base._task.async_val = False
    base._task.action = "config"
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


def _answer(monkeypatch, plugin) -> None:
    """Answer every getconf the way the run plugin would.

    A variable the fabricated host does not know about answers
    non-zero, which is what a getconf that refuses one looks like.
    """

    def mock_run(commands: Any, **kwargs: Any) -> list[dict[str, Any]]:
        results = []
        for request in commands:
            variable = request["command"][1]
            answered = ANSWERS.get(variable)
            results.append(
                dict(
                    request,
                    rc=0 if answered is not None else 1,
                    stdout=answered or "",
                    stdout_lines=[answered] if answered else [],
                    stderr="",
                    stderr_lines=[],
                )
            )
        return results

    monkeypatch.setattr(plugin, "_run", mock_run)


def test_the_module_answers_what_the_host_limits(monkeypatch, plugin) -> None:
    """Test the variables come back typed the way the host printed."""
    _answer(monkeypatch, plugin)

    result = plugin.run(task_vars={})

    assert result["changed"] is False
    assert result["config"]["ARG_MAX"] == 1048576
    assert result["config"]["_POSIX_VERSION"] == 200809


def test_a_variable_the_host_does_not_limit_is_null(
    monkeypatch, plugin
) -> None:
    """Test undefined is null, which is what undefined means here."""
    _answer(monkeypatch, plugin)

    result = plugin.run(task_vars={})

    assert result["config"]["SYMLOOP_MAX"] is None


def test_a_variable_the_host_refused_is_left_out(
    monkeypatch, plugin
) -> None:
    """Test a refusal is absence rather than a null.

    Null is already spent on a variable the host has and does not
    limit, so a getconf that would not answer says nothing at all.
    """
    _answer(monkeypatch, plugin)

    result = plugin.run(task_vars={})

    assert "LINE_MAX" not in result["config"]


def test_the_namespace_names_the_command_that_asked(
    monkeypatch, plugin
) -> None:
    """Test one command and nothing else.

    The variables are the fact rather than evidence for one, so there
    is no config kind here: a fact is not evidence for itself.
    """
    _answer(monkeypatch, plugin)

    result = plugin.run(task_vars={})

    assert result["evidence"] == {"commands": ["getconf"]}


def test_nothing_is_published_as_facts_unless_asked(
    monkeypatch, plugin
) -> None:
    """Test the returns stand alone; gather is what sets facts."""
    _answer(monkeypatch, plugin)

    result = plugin.run(task_vars={})

    assert "ansible_facts" not in result
    assert "o0_os" not in result


def test_gather_publishes_one_namespace_naming_this_module(
    monkeypatch, plugin
) -> None:
    """Test the fact is the subset's shape, named by its composer."""
    _answer(monkeypatch, plugin)
    plugin._task.args = {"gather": True}

    result = plugin.run(task_vars={})

    facts = result["ansible_facts"]
    assert list(facts) == ["o0_os"]
    assert facts["o0_os"]["config"] == result["config"]
    assert facts["o0_os"]["origins"] == ["o0_o.posix.config"]
    assert facts["o0_os"]["evidence"] == {"commands": ["getconf"]}


def test_a_host_that_answered_nothing_publishes_no_facts(
    monkeypatch, plugin
) -> None:
    """Test a host with no getconf leaves the namespace unpublished.

    An empty answer and no answer are not the same claim, so the
    return says it was asked and the fact says nothing.
    """

    def mock_run(commands: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return [
            dict(
                request,
                rc=127,
                stdout="",
                stdout_lines=[],
                stderr="not found",
                stderr_lines=["not found"],
            )
            for request in commands
        ]

    monkeypatch.setattr(plugin, "_run", mock_run)
    plugin._task.args = {"gather": True}

    result = plugin.run(task_vars={})

    assert result["config"] == {}
    assert "ansible_facts" not in result
