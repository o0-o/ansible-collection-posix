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


def test_timezone_full_detection(monkeypatch, plugin) -> None:
    """Test full timezone detection with all components."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == ["env"]:
            return {"rc": 0, "stdout": "TZ=America/New_York\n"}
        if cmd == ["test", "-e", "/etc/localtime"]:
            return {"rc": 0}
        if cmd == ["readlink", "/etc/localtime"]:
            return {
                "rc": 0,
                "stdout": "/var/db/timezone/zoneinfo/America/New_York\n",
            }
        if cmd == ["ls", "-l", "/etc/localtime"]:
            return {"rc": 1}
        if cmd == ["test", "-f", "/usr/share/zoneinfo/America/New_York"]:
            return {"rc": 0}
        if cmd == [
            "strings",
            "-n",
            "1",
            "/usr/share/zoneinfo/America/New_York",
        ]:
            return {
                "rc": 0,
                "stdout": "TZif2\nSomething\nEST5EDT,M3.2.0,M11.1.0\n",
            }
        if cmd == ["date", "+%Z"]:
            return {"rc": 0, "stdout": "EDT\n"}
        if cmd == ["date", "+%z"]:
            return {"rc": 0, "stdout": "-0400\n"}
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)
    tz = plugin._get_timezone(task_vars={})
    assert tz["name"] == "America/New_York"
    assert tz["zone"] == tz["name"]
    assert tz["posix"] == "EST5EDT,M3.2.0,M11.1.0"
    standard = tz["standard"]
    assert standard["abbr"] == "EST"
    assert standard["offset"] == "-05:00"
    daylight = tz["daylight"]
    assert daylight["abbr"] == "EDT"
    assert daylight["offset"] == "-04:00"
    start = daylight["start"]
    assert start["month"] == 3
    assert start["week"] == 2
    assert start["weekday"] == 0
    assert start["time"] == "02:00"
    end = daylight["end"]
    assert end["month"] == 11
    assert end["week"] == 1
    assert end["weekday"] == 0
    assert end["time"] == "02:00"
    config = tz["config"]["/etc/localtime"]
    assert config["link"] == "/var/db/timezone/zoneinfo/America/New_York"
    assert tz["abbr"] == "EDT"
    assert tz["offset"] == "-0400"


def test_timezone_tail_fallback(monkeypatch, plugin) -> None:
    """Test fallback to /etc/timezone and tail command."""

    tail_chunk = "TZif3\nData\nMST7\n"

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == ["env"]:
            return {"rc": 1}
        if cmd == ["test", "-e", "/etc/localtime"]:
            return {"rc": 0}
        if cmd == ["readlink", "/etc/localtime"]:
            return {"rc": 1}
        if cmd == ["ls", "-l", "/etc/localtime"]:
            return {
                "rc": 0,
                "stdout": (
                    "/etc/localtime -> "
                    "/usr/share/zoneinfo/America/Phoenix\n"
                ),
            }
        if cmd == ["test", "-f", "/etc/timezone"]:
            return {"rc": 0}
        if cmd == ["cat", "/etc/timezone"]:
            return {"rc": 0, "stdout": "America/Phoenix\n"}
        if cmd == ["test", "-f", "/usr/share/zoneinfo/America/Phoenix"]:
            return {"rc": 0}
        if cmd == [
            "strings",
            "-n",
            "1",
            "/usr/share/zoneinfo/America/Phoenix",
        ]:
            return {"rc": 1}
        if cmd == ["tail", "-c", "512", "/usr/share/zoneinfo/America/Phoenix"]:
            return {"rc": 0, "stdout": tail_chunk}
        if cmd == ["date", "+%Z"]:
            return {"rc": 0, "stdout": "MST\n"}
        if cmd == ["date", "+%z"]:
            return {"rc": 0, "stdout": "-0700\n"}
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)
    tz = plugin._get_timezone(task_vars={})
    assert tz["name"] == "America/Phoenix"
    assert tz["zone"] == tz["name"]
    assert tz["posix"] == "MST7"
    standard = tz["standard"]
    assert standard["abbr"] == "MST"
    assert standard["offset"] == "-07:00"
    config = tz["config"]["/etc/localtime"]
    assert config["link"] == "/usr/share/zoneinfo/America/Phoenix"
    assert "daylight" not in tz
    assert tz["abbr"] == "MST"
    assert tz["offset"] == "-0700"


def test_timezone_detection_failure(monkeypatch, plugin) -> None:
    """Test that RuntimeError is raised when detection fails."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)
    with pytest.raises(
        RuntimeError, match="Timezone detection methods exhausted"
    ):
        plugin._get_timezone(task_vars={})
