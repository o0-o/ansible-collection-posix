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

"""Tests for the uptime action plugin."""

from __future__ import annotations

from datetime import timezone
from typing import Generator

import pytest

from ansible.errors import AnsibleActionFail

from ansible_collections.o0_o.posix.plugins.action.uptime import ActionModule


@pytest.fixture
def plugin(base) -> Generator[ActionModule, None, None]:
    base._task.async_val = False
    base._task.action = "uptime"
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


def test_uptime_success(monkeypatch: pytest.MonkeyPatch, plugin) -> None:
    cmd_output = {"rc": 0, "stdout": "ignored"}
    parsed = {
        "uptime": {
            "elapsed": {"seconds": 123},
            "started": {"iso8601": "2025-01-01T00:00:00Z"},
        },
        "load": {"1": 0.5, "5": 0.4, "15": 0.3},
        "login_sessions": 2,
    }

    monkeypatch.setattr(plugin, "_cmd", lambda *_args, **_kwargs: cmd_output)
    monkeypatch.setattr(
        plugin, "_get_target_timezone", lambda _tv: timezone.utc
    )
    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.action.uptime.parse_uptime",
        lambda data, now=None: parsed,
    )

    result = plugin.run(task_vars={})

    assert result["changed"] is False
    assert result["uptime"] == parsed["uptime"]
    assert result["load"] == parsed["load"]
    assert result["login_sessions"] == 2


def test_uptime_command_failure(
    monkeypatch: pytest.MonkeyPatch, plugin
) -> None:
    def cmd_mock(args, **_kwargs):
        if args == ["date", "+%z"]:
            return {"rc": 0, "stdout": "+0000"}
        return {"rc": 1, "stderr": "boom"}

    monkeypatch.setattr(plugin, "_cmd", cmd_mock)

    with pytest.raises(AnsibleActionFail, match="uptime command failed"):
        plugin.run(task_vars={})


def test_uptime_parse_failure(monkeypatch: pytest.MonkeyPatch, plugin) -> None:
    def cmd_mock(args, **_kwargs):
        if args == ["date", "+%z"]:
            return {"rc": 0, "stdout": "+0000"}
        return {"rc": 0, "stdout": "bad"}

    monkeypatch.setattr(plugin, "_cmd", cmd_mock)

    def raise_error(data: object, now=None) -> dict[str, object]:
        raise ValueError("parse")

    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.action.uptime.parse_uptime",
        raise_error,
    )

    with pytest.raises(
        AnsibleActionFail, match="Failed to parse uptime output"
    ):
        plugin.run(task_vars={})
