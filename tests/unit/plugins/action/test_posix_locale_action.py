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

from ansible_collections.o0_o.posix.plugins.action.locale import ActionModule


@pytest.fixture
def plugin(base) -> Generator[ActionModule, None, None]:
    """Create an ActionModule instance for locale detection tests."""
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


def test_locale_from_locale_command(monkeypatch, plugin) -> None:
    """Test successful parsing of locale command output into categories."""

    locale_output = """
LANG="en_US.UTF-8"
LC_CTYPE="en_US.UTF-8"
LC_COLLATE="en_US.UTF-8"
LC_MESSAGES="en_US.UTF-8"
LC_MONETARY="en_US.UTF-8"
LC_NUMERIC="en_US.UTF-8"
LC_TIME="en_US.UTF-8"
LC_ALL=
""".strip()

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == ["locale"]:
            return {"rc": 0, "stdout": locale_output}
        if cmd == ["env"]:
            return {"rc": 1}
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)
    locale = plugin._get_locale(task_vars={})
    assert locale == {
        "language": "en_US.UTF-8",
        "all": None,
        "characters": "en_US.UTF-8",
        "collation": "en_US.UTF-8",
        "messages": "en_US.UTF-8",
        "monetary": "en_US.UTF-8",
        "numeric": "en_US.UTF-8",
        "time": "en_US.UTF-8",
    }


def test_locale_fallback_to_env(monkeypatch, plugin) -> None:
    """Test fallback to environment variables when locale command fails."""

    env_output = """
LANG=en_GB.UTF-8
LC_ALL=en_GB.UTF-8
LC_TIME=en_GB.UTF-8
""".strip()

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == ["locale"]:
            return {"rc": 1}
        if cmd == ["env"]:
            return {"rc": 0, "stdout": env_output}
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)
    locale = plugin._get_locale(task_vars={})
    assert locale == {
        "language": "en_GB.UTF-8",
        "all": "en_GB.UTF-8",
        "characters": None,
        "collation": None,
        "messages": None,
        "monetary": None,
        "numeric": None,
        "time": "en_GB.UTF-8",
    }


def test_locale_detection_failure(monkeypatch, plugin) -> None:
    """Test that RuntimeError is raised when all detection methods fail."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)
    with pytest.raises(
        RuntimeError, match="Locale detection methods exhausted"
    ):
        plugin._get_locale(task_vars={})
