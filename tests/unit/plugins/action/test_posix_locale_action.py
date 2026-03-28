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

"""Unit tests for locale action plugin."""

from __future__ import annotations

from typing import Generator

import pytest

from ansible_collections.o0_o.posix.plugins.action.locale import (
    ActionModule,
)


@pytest.fixture
def plugin(base) -> Generator[ActionModule, None, None]:
    """Create an ActionModule instance for locale tests."""
    base._task.async_val = False
    base._task.action = "locale"
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


def test_run_returns_locale_data(monkeypatch, plugin) -> None:
    """Test run returns parsed locale categories."""

    def mock_run(commands, **kwargs):
        return []

    monkeypatch.setattr(plugin, "_run", mock_run)

    from ansible_collections.o0_o.posix.plugins.action import (
        locale as locale_mod,
    )

    monkeypatch.setattr(
        locale_mod,
        "process_locale_command_results",
        lambda results: (
            {
                "language": "en_US.UTF-8",
                "all": None,
                "characters": "en_US.UTF-8",
            },
            [],
        ),
    )

    result = plugin.run(task_vars={})

    assert result["locale"]["language"] == "en_US.UTF-8"
    assert result["locale"]["characters"] == "en_US.UTF-8"
    assert result["changed"] is False


def test_run_emits_warnings_on_errors(monkeypatch, plugin) -> None:
    """Test that processing errors emit warnings."""

    def mock_run(commands, **kwargs):
        return []

    monkeypatch.setattr(plugin, "_run", mock_run)

    from ansible_collections.o0_o.posix.plugins.action import (
        locale as locale_mod,
    )

    monkeypatch.setattr(
        locale_mod,
        "process_locale_command_results",
        lambda results: (
            {},
            [ValueError("locale failed")],
        ),
    )

    result = plugin.run(task_vars={})

    assert result["locale"] == {}
    plugin._display.warning.assert_called()
