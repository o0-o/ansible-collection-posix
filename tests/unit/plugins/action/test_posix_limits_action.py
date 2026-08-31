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

"""Unit tests for the limits action plugin."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Generator

import pytest

from ansible_collections.o0_o.posix.plugins.action.limits import ActionModule

CORPUS = (
    Path(__file__).parents[1] / "module_utils" / "files" / "ulimit_macos.txt"
)


@pytest.fixture
def plugin(base) -> Generator[ActionModule, None, None]:
    """Create an ActionModule instance for limits tests."""
    base._task.async_val = False
    base._task.action = "limits"
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


def _answer(monkeypatch, plugin, uid: str = "0") -> None:
    """Answer the probes the way a session with limits would."""
    corpus = CORPUS.read_text()

    def mock_run(commands: Any, **kwargs: Any) -> list[dict[str, Any]]:
        results = []
        for request in commands:
            stdout = corpus if request["type"] == "ulimit" else uid
            results.append(
                dict(
                    request,
                    rc=0,
                    stdout=stdout,
                    stdout_lines=stdout.splitlines(),
                    stderr="",
                    stderr_lines=[],
                )
            )
        return results

    monkeypatch.setattr(plugin, "_run", mock_run)


def test_the_session_answers_what_it_is_limited_to(
    monkeypatch, plugin
) -> None:
    """Test each resource carries both ceilings and its unit."""
    _answer(monkeypatch, plugin)

    result = plugin.run(task_vars={})

    assert result["changed"] is False
    assert result["limits"]["processes"] == {"soft": 10666, "hard": 16000}
    assert result["limits"]["stack"] == {
        "soft": 8176,
        "hard": 65520,
        "unit": "kbytes",
    }


def test_an_unlimited_ceiling_is_null(monkeypatch, plugin) -> None:
    """Test unlimited is null, so a resource with no cap is present.

    A consumer reading a resource's hard ceiling gets an answer
    either way, and the answer for uncapped is not a missing key.
    """
    _answer(monkeypatch, plugin)

    result = plugin.run(task_vars={})

    assert result["limits"]["cpu_time"]["soft"] is None
    assert result["limits"]["cpu_time"]["hard"] is None


def test_the_answer_names_the_uid_it_came_from(monkeypatch, plugin) -> None:
    """Test who answered comes back beside what they are limited to.

    A become chain means the identity in the play is not always the
    identity that answered, and a limit is only meaningful beside the
    identity it applies to.
    """
    _answer(monkeypatch, plugin, uid="1000")

    result = plugin.run(task_vars={})

    assert result["uid"] == 1000


def test_the_result_names_the_builtin_it_asked(monkeypatch, plugin) -> None:
    """Test ulimit is named rather than the shell that read it back.

    The probe is a script, so argv names sh; a builtin is a command a
    fact may name like any other, and it is what was asked.
    """
    _answer(monkeypatch, plugin)

    result = plugin.run(task_vars={})

    assert result["evidence"] == {"commands": ["id", "ulimit"]}


def test_nothing_is_published_as_facts(monkeypatch, plugin) -> None:
    """Test the answer stands alone and outlives nothing.

    A limit belongs to the session that answered, and a fact outlives
    the task that gathered it, so this publishes none.
    """
    _answer(monkeypatch, plugin)

    result = plugin.run(task_vars={})

    assert "ansible_facts" not in result


def test_a_session_that_would_not_say_reports_no_limits(
    monkeypatch, plugin
) -> None:
    """Test an empty mapping says the question was asked.

    A session whose shell has no ulimit is not a session without
    limits, so the key is there and holds nothing.
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

    result = plugin.run(task_vars={})

    assert result["limits"] == {}
    assert result["uid"] is None


def test_the_probe_runs_in_check_mode(monkeypatch, plugin) -> None:
    """Test asking is not a change, so check mode still asks.

    A check mode run that skipped the probe would read as a session
    with no limits, which is a different claim.
    """
    asked: list[bool] = []
    corpus = CORPUS.read_text()

    def mock_run(commands: Any, **kwargs: Any) -> list[dict[str, Any]]:
        asked.append(kwargs.get("check_mode"))
        return [
            dict(
                request,
                rc=0,
                stdout=corpus if request["type"] == "ulimit" else "0",
                stdout_lines=[],
                stderr="",
                stderr_lines=[],
            )
            for request in commands
        ]

    monkeypatch.setattr(plugin, "_run", mock_run)
    plugin._task.check_mode = True

    result = plugin.run(task_vars={})

    assert asked == [False]
    assert result["limits"]["processes"]["soft"] == 10666
