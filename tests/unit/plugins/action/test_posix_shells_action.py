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

"""Unit tests for the shells action plugin."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Generator, Optional

import pytest

from ansible_collections.o0_o.posix.plugins.action.facts import (
    ActionModule as FactsActionModule,
)
from ansible_collections.o0_o.posix.plugins.action.shells import ActionModule

# A real login run of /bin/sh, captured off a host
CORPUS = (
    Path(__file__).parents[1]
    / "module_utils"
    / "files"
    / "shell_config_macos.txt"
)

SHELLS_FILE = "\n".join(
    [
        "# List of acceptable shells",
        "/bin/sh",
        "/bin/zsh",
    ]
)


def _answer(
    monkeypatch,
    plugin: ActionModule,
    shells_file: Optional[str] = SHELLS_FILE,
    uid: str = "501",
) -> list[list[dict[str, Any]]]:
    """Answer the read, the uid and the probes the module asks for.

    :param monkeypatch: The pytest monkeypatch fixture
    :param ActionModule plugin: Action instance to patch
    :param Optional[str] shells_file: The file's content, or None for
        a host that has no /etc/shells
    :param str uid: What the host says the effective uid is
    :returns list[list[dict[str, Any]]]: The batches the module issued
    """
    batches: list[list[dict[str, Any]]] = []
    corpus = CORPUS.read_text()

    def mock_run(commands: Any, **kwargs: Any) -> list[dict[str, Any]]:
        batches.append(commands)
        answered = []
        for request in commands:
            kind = request["type"]
            if kind == "effective_uid":
                answered.append({**request, "rc": 0, "stdout": uid})
            elif kind.startswith("shell_"):
                answered.append({**request, "rc": 0, "stdout": corpus})
            elif shells_file is None:
                answered.append(
                    {**request, "rc": 1, "stdout": "", "stderr": "no file"}
                )
            else:
                answered.append({**request, "rc": 0, "stdout": shells_file})
        return answered

    monkeypatch.setattr(plugin, "_run", mock_run)
    return batches


@pytest.fixture
def plugin(monkeypatch, base) -> Generator[ActionModule, None, None]:
    """Create an ActionModule instance for shells tests."""
    base._task.async_val = False
    base._task.action = "shells"
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

    # A shell's own file metadata comes from the read action plugin,
    # which is exercised by its own tests
    monkeypatch.setattr(plugin, "_read", lambda **kwargs: {"paths": {}})
    yield plugin


def test_the_names_come_out_of_the_file(monkeypatch, plugin) -> None:
    """Test every shell the host names is a key."""
    _answer(monkeypatch, plugin)

    result = plugin.run(task_vars={})

    assert result["changed"] is False
    assert sorted(result["shells"]) == ["/bin/sh", "/bin/zsh"]


def test_a_shell_that_was_named_and_not_run_is_empty(
    monkeypatch, plugin
) -> None:
    """Test the key is the claim and the empty value is the truth.

    Nothing runs every shell a host names: a probe is a shell run, and
    running each one on the chance somebody logs in with it is a cost
    with no answer attached.
    """
    _answer(monkeypatch, plugin)

    result = plugin.run(task_vars={})

    assert result["shells"]["/bin/zsh"] == {}


def test_the_shell_that_was_run_says_what_it_produced(
    monkeypatch, plugin
) -> None:
    """Test the row is what the login run made, under its home."""
    _answer(monkeypatch, plugin)

    result = plugin.run(task_vars={})
    row = result["shells"]["/bin/sh"]["homes"]["/dev/null"]

    assert row["umask"] == "0022"
    assert row["env"]["PATH"]
    # The keys the row was filed under are not fields of it
    assert "HOME" not in row["env"]
    assert "SHELL" not in row["env"]


def test_the_entry_names_what_was_asked_of_that_shell(
    monkeypatch, plugin
) -> None:
    """Test the shell is named beside what the script put to it."""
    _answer(monkeypatch, plugin)

    result = plugin.run(task_vars={})
    entry = result["shells"]["/bin/sh"]

    assert entry["evidence"]["commands"] == [
        "alias",
        "env",
        "locale",
        "sh",
        "umask",
    ]
    assert entry["origins"] == ["o0_o.posix.shells"]


def test_the_file_lands_at_its_own_path(monkeypatch, plugin) -> None:
    """Test what a file names is a fact about that file.

    The bytes under content, the names they hold under config, and the
    command that read it as the evidence - the file is the fact rather
    than evidence for one.
    """
    _answer(monkeypatch, plugin)

    result = plugin.run(task_vars={})
    entry = result["o0_paths"]["/etc/shells"]

    assert entry["content"] == SHELLS_FILE
    assert entry["config"] == ["/bin/sh", "/bin/zsh"]
    assert entry["evidence"] == {"commands": ["cat"]}
    assert entry["origins"] == ["o0_o.posix.shells"]


def test_a_host_with_no_shells_file_leaves_the_path_out(
    monkeypatch, plugin
) -> None:
    """Test a read that failed files no null.

    A cat that failed cannot tell a file that is not there from one it
    could not read, and null is the store's word for confirmed absent.
    The probe still runs, because what /bin/sh does is not a claim the
    file was making.
    """
    _answer(monkeypatch, plugin, shells_file=None)

    result = plugin.run(task_vars={})

    assert "/etc/shells" not in result["o0_paths"]
    assert list(result["shells"]) == ["/bin/sh"]


def test_nothing_is_published_as_facts_unless_asked(
    monkeypatch, plugin
) -> None:
    """Test the returns stand alone; gather is what sets facts."""
    _answer(monkeypatch, plugin)

    result = plugin.run(task_vars={})

    assert "ansible_facts" not in result


def test_gather_publishes_the_names_a_gather_publishes(
    monkeypatch, plugin
) -> None:
    """Test the fact is the gather's shape under the gather's names."""
    _answer(monkeypatch, plugin)
    plugin._task.args = {"gather": True}

    result = plugin.run(task_vars={})
    facts = result["ansible_facts"]

    assert sorted(facts) == ["o0_paths", "o0_shells"]
    assert facts["o0_shells"] == result["shells"]
    assert facts["o0_paths"] == result["o0_paths"]


def test_the_shell_to_observe_is_the_task_s_to_name(
    monkeypatch, plugin
) -> None:
    """Test the option decides which shell the system layer runs."""
    batches = _answer(monkeypatch, plugin)
    plugin._task.args = {"shell": "/bin/ksh"}

    result = plugin.run(task_vars={})

    asked = [
        request["args"]["shell"]
        for batch in batches
        for request in batch
        if request["type"] == "shell_config"
    ]
    assert asked == ["/bin/ksh"]
    # And the shell that answered is a key, whether the file named it
    assert "/bin/ksh" in result["shells"]


def test_a_shell_the_store_says_is_absent_is_not_run(
    monkeypatch, plugin
) -> None:
    """Test a confirmed absence is believed rather than re-asked.

    The store is consulted rather than trusted for a positive: a path
    it has never been asked about is not a path known to be missing.
    """
    batches = _answer(monkeypatch, plugin)

    result = plugin.run(task_vars={"o0_paths": {"/bin/sh": None}})

    asked = [
        request
        for batch in batches
        for request in batch
        if request["type"].startswith("shell_")
    ]
    assert asked == []
    assert result["shells"]["/bin/sh"] == {}


def test_the_probe_runs_in_check_mode(monkeypatch, plugin) -> None:
    """Test running a shell to read its configuration is not a change.

    A check mode run that skipped it would read as a host whose shells
    do nothing, which is a different claim.
    """
    _answer(monkeypatch, plugin)
    plugin._task.check_mode = True

    result = plugin.run(task_vars={})

    assert result["shells"]["/bin/sh"]["homes"]["/dev/null"]["umask"] == (
        "0022"
    )


def test_one_planning_serves_both_producers() -> None:
    """Test the gather and this module plan the probes one way.

    A shell fact is what a login shell turned out to do, so two
    producers planning it differently would publish two answers to one
    question.
    """
    assert (
        ActionModule._shell_probes is FactsActionModule._shell_probes
    )
    assert (
        ActionModule._composed_shells is FactsActionModule._composed_shells
    )
