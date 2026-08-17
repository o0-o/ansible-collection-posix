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

from ansible_collections.o0_o.posix.plugins.action.timezone import ActionModule


@pytest.fixture
def plugin(base) -> Generator[ActionModule, None, None]:
    """Create an ActionModule instance for timezone detection tests."""
    base._task.async_val = False
    base._task.action = "timezone"
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


def test_run_returns_timezone_data(monkeypatch, plugin) -> None:
    """Test run returns the detected abbreviation and offset."""

    def mock_run(commands, **kwargs):
        return []

    monkeypatch.setattr(plugin, "_run", mock_run)

    from ansible_collections.o0_o.posix.plugins.action import (
        timezone as timezone_mod,
    )

    monkeypatch.setattr(
        timezone_mod,
        "process_timezone_command_results",
        lambda results: (
            {
                "o0_os": {
                    "timezone": {
                        "abbreviation": "EDT",
                        "offset": "-0400",
                    }
                }
            },
            [],
        ),
    )

    result = plugin.run(task_vars={})

    assert result["timezone"]["abbreviation"] == "EDT"
    assert result["timezone"]["offset"] == "-0400"
    assert result["changed"] is False


def test_run_emits_warnings_on_errors(monkeypatch, plugin) -> None:
    """Test that detection failures emit warnings and empty facts."""

    def mock_run(commands, **kwargs):
        return []

    monkeypatch.setattr(plugin, "_run", mock_run)

    from ansible_collections.o0_o.posix.plugins.action import (
        timezone as timezone_mod,
    )

    monkeypatch.setattr(
        timezone_mod,
        "process_timezone_command_results",
        lambda results: (
            {},
            [ValueError("Empty timezone output")],
        ),
    )

    result = plugin.run(task_vars={})

    assert result["timezone"] == {}
    plugin._display.warning.assert_called()


def test_run_calls_run_with_correct_kwargs(monkeypatch, plugin) -> None:
    """Test that _run is called with parallel and check_mode."""
    captured = {}

    def mock_run(commands, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(plugin, "_run", mock_run)

    from ansible_collections.o0_o.posix.plugins.action import (
        timezone as timezone_mod,
    )

    monkeypatch.setattr(
        timezone_mod,
        "process_timezone_command_results",
        lambda results: ({}, []),
    )

    plugin.run(task_vars={})

    assert captured["parallel"] is True
    assert captured["fail_fast"] is False
    assert captured["check_mode"] is False
