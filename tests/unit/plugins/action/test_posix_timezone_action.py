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
    """Create an ActionModule instance with patched dependencies."""

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
    return plugin


def test_timezone_from_etc_timezone(monkeypatch, plugin) -> None:
    """Detect timezone from /etc/timezone file."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == ["test", "-f", "/etc/timezone"]:
            return {"rc": 0}
        if cmd == ["cat", "/etc/timezone"]:
            return {"rc": 0, "stdout": "Europe/Paris\n"}
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)
    tz = plugin._get_timezone(task_vars={})
    assert tz["name"] == "Europe/Paris"
    assert tz["config"]["path"] == "/etc/timezone"


def test_timezone_from_localtime_symlink(monkeypatch, plugin) -> None:
    """Detect timezone by parsing /etc/localtime symlink."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == ["test", "-f", "/etc/timezone"]:
            return {"rc": 1}
        if cmd == ["readlink", "/etc/localtime"]:
            return {
                "rc": 0,
                "stdout": "/var/db/timezone/zoneinfo/America/Los_Angeles\n",
            }
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)
    tz = plugin._get_timezone(task_vars={})
    assert tz["name"] == "America/Los_Angeles"
    assert tz["config"]["path"] == "/etc/localtime"


def test_timezone_from_systemsetup(monkeypatch, plugin) -> None:
    """Use systemsetup on macOS when symlink method fails."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == ["test", "-f", "/etc/timezone"]:
            return {"rc": 1}
        if cmd == ["readlink", "/etc/localtime"]:
            return {"rc": 1}
        if cmd == ["ls", "-l", "/etc/localtime"]:
            return {"rc": 1}
        if cmd == ["systemsetup", "-gettimezone"]:
            return {"rc": 0, "stdout": "Time Zone: Europe/Berlin\n"}
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)
    tz = plugin._get_timezone(task_vars={})
    assert tz["name"] == "Europe/Berlin"
    assert tz["config"]["command"] == "systemsetup -gettimezone"


def test_timezone_from_timedatectl(monkeypatch, plugin) -> None:
    """Use timedatectl when other methods fail."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == ["test", "-f", "/etc/timezone"]:
            return {"rc": 1}
        if cmd == ["readlink", "/etc/localtime"]:
            return {"rc": 1}
        if cmd == ["ls", "-l", "/etc/localtime"]:
            return {"rc": 1}
        if cmd == ["systemsetup", "-gettimezone"]:
            return {"rc": 1}
        if cmd == ["timedatectl", "show", "-p", "Timezone", "--value"]:
            return {"rc": 0, "stdout": "Asia/Tokyo\n"}
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)
    tz = plugin._get_timezone(task_vars={})
    assert tz["name"] == "Asia/Tokyo"
    assert tz["config"]["command"] == "timedatectl show -p Timezone --value"


def test_timezone_fallback_abbr(monkeypatch, plugin) -> None:
    """Fallback to timezone abbreviation from date +%Z."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == ["test", "-f", "/etc/timezone"]:
            return {"rc": 1}
        if cmd == ["readlink", "/etc/localtime"]:
            return {"rc": 1}
        if cmd == ["ls", "-l", "/etc/localtime"]:
            return {"rc": 1}
        if cmd == ["systemsetup", "-gettimezone"]:
            return {"rc": 1}
        if cmd == ["timedatectl", "show", "-p", "Timezone", "--value"]:
            return {"rc": 1}
        if cmd == ["date", "+%Z"]:
            return {"rc": 0, "stdout": "UTC\n"}
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)
    tz = plugin._get_timezone(task_vars={})
    assert tz["abbr"] == "UTC"
    assert tz["config"]["command"] == "date +%Z"
