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

from ansible_collections.o0_o.posix.plugins.action.which import ActionModule


@pytest.fixture
def plugin(base) -> Generator[ActionModule, None, None]:
    """Create an ActionModule instance for which resolution tests."""

    base._task.async_val = False
    base._task.action = "which"
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


def test_which_finds_command(monkeypatch, plugin) -> None:
    """Test resolving a command path successfully."""

    monkeypatch.setattr(
        plugin, "_which", lambda cmd, task_vars=None: "/bin/date"
    )
    plugin._task.args = {"command": "date"}
    result = plugin.run(task_vars={})
    assert result["changed"] is False
    assert result["path"] == "/bin/date"


def test_which_files_the_resolution_under_its_path(
    monkeypatch, plugin
) -> None:
    """Test a resolution is a fact about the file it landed on, filed
    in the same store a compliance sweep fills, and marked as inferred
    because a lookup is not a permission probe."""

    monkeypatch.setattr(
        plugin, "_which", lambda cmd, task_vars=None: "/bin/date"
    )
    plugin._task.args = {"command": "date"}
    result = plugin.run(task_vars={})

    assert result["o0_paths"] == {
        "/bin/date": {
            "executable": True,
            "executable_evidence": "inferred",
        }
    }


def test_which_not_found(monkeypatch, plugin) -> None:
    """Test that a missing command resolves to a null path."""

    monkeypatch.setattr(plugin, "_which", lambda cmd, task_vars=None: None)
    plugin._task.args = {"command": "no-such-command"}
    result = plugin.run(task_vars={})
    assert result["changed"] is False
    assert result["path"] is None


def test_which_not_found_names_no_path(monkeypatch, plugin) -> None:
    """Test one lookup that missed names no path it was not at, so it
    files no confirmed absence it cannot evidence."""

    monkeypatch.setattr(plugin, "_which", lambda cmd, task_vars=None: None)
    plugin._task.args = {"command": "no-such-command"}
    result = plugin.run(task_vars={})

    assert "o0_paths" not in result


def test_which_builtin(monkeypatch, plugin) -> None:
    """Test that a shell built-in resolves to its bare name."""

    monkeypatch.setattr(plugin, "_which", lambda cmd, task_vars=None: "echo")
    plugin._task.args = {"command": "echo"}
    result = plugin.run(task_vars={})
    assert result["changed"] is False
    assert result["path"] == "echo"


def test_which_builtin_files_no_path(monkeypatch, plugin) -> None:
    """Test a builtin is not a file, so it leaves the path store
    alone rather than filing an entry keyed by a bare name."""

    monkeypatch.setattr(plugin, "_which", lambda cmd, task_vars=None: "echo")
    plugin._task.args = {"command": "echo"}
    result = plugin.run(task_vars={})

    assert "o0_paths" not in result


def test_which_refuses_a_path_the_store_cannot_key(
    monkeypatch, plugin
) -> None:
    """Test a host that answers with a path the store will not key
    warns and still answers, rather than failing the task over the
    shape of a fact."""

    monkeypatch.setattr(
        plugin, "_which", lambda cmd, task_vars=None: "/usr/bin//date"
    )
    plugin._task.args = {"command": "date"}
    result = plugin.run(task_vars={})

    assert result["path"] == "/usr/bin//date"
    assert "o0_paths" not in result
    plugin._display.warning.assert_called_once()
