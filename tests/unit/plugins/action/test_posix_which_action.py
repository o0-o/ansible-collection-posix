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


def test_which_not_found(monkeypatch, plugin) -> None:
    """Test that a missing command resolves to a null path."""

    monkeypatch.setattr(plugin, "_which", lambda cmd, task_vars=None: None)
    plugin._task.args = {"command": "no-such-command"}
    result = plugin.run(task_vars={})
    assert result["changed"] is False
    assert result["path"] is None


def test_which_builtin(monkeypatch, plugin) -> None:
    """Test that a shell built-in resolves to its bare name."""

    monkeypatch.setattr(plugin, "_which", lambda cmd, task_vars=None: "echo")
    plugin._task.args = {"command": "echo"}
    result = plugin.run(task_vars={})
    assert result["changed"] is False
    assert result["path"] == "echo"
