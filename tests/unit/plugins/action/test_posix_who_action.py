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

"""Tests for the who action plugin."""

from __future__ import annotations

from datetime import timedelta, timezone
from typing import Any, Dict, Generator

import pytest
from ansible.errors import AnsibleActionFail

from ansible_collections.o0_o.posix.plugins.action.who import ActionModule


@pytest.fixture
def plugin(base) -> Generator[ActionModule, None, None]:
    base._task.async_val = False
    base._task.action = "who"
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
    yield plugin


def test_who_success(
    monkeypatch: pytest.MonkeyPatch, plugin: ActionModule
) -> None:
    cmd_result = {"rc": 0, "stdout": "ignored"}
    parsed = {"sessions": [{"user": "alice"}]}

    monkeypatch.setattr(plugin, "_cmd", lambda *_args, **_kwargs: cmd_result)
    monkeypatch.setattr(
        plugin, "_get_target_timezone", lambda _tv: timezone.utc
    )
    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.action.who.parse_who",
        lambda value, now=None: parsed,
    )

    result = plugin.run(task_vars={})

    assert result["changed"] is False
    assert result["sessions"] == parsed["sessions"]


def test_who_command_failure(
    monkeypatch: pytest.MonkeyPatch, plugin: ActionModule
) -> None:
    def cmd_mock(args, **_kwargs):
        if args == ["date", "+%z"]:
            return {"rc": 0, "stdout": "+0000"}
        return {"rc": 1, "stderr": "failure"}

    monkeypatch.setattr(plugin, "_cmd", cmd_mock)

    with pytest.raises(AnsibleActionFail, match="who command failed"):
        plugin.run(task_vars={})


def test_who_parse_failure(
    monkeypatch: pytest.MonkeyPatch, plugin: ActionModule
) -> None:
    def cmd_mock(args, **_kwargs):
        if args == ["date", "+%z"]:
            return {"rc": 0, "stdout": "+0000"}
        return {"rc": 0}

    monkeypatch.setattr(plugin, "_cmd", cmd_mock)

    def raise_error(data: object, now=None) -> Dict[str, Any]:
        raise ValueError("parse")

    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.action.who.parse_who",
        raise_error,
    )

    with pytest.raises(AnsibleActionFail, match="Failed to parse who output"):
        plugin.run(task_vars={})


class TestTimezoneOffset:
    """Test timezone offset parsing and detection."""

    @pytest.mark.parametrize(
        "offset_str,expected_hours,expected_minutes",
        [
            ("-0400", -4, 0),
            ("+0000", 0, 0),
            ("+0530", 5, 30),
            ("-1100", -11, 0),
            ("+1245", 12, 45),
        ],
    )
    def test_parse_timezone_offset_valid(
        self,
        plugin: ActionModule,
        offset_str: str,
        expected_hours: int,
        expected_minutes: int,
    ) -> None:
        """Test parsing valid timezone offset strings."""
        tz = plugin._parse_timezone_offset(offset_str)
        expected = timezone(
            timedelta(hours=expected_hours, minutes=expected_minutes)
        )
        assert tz == expected

    @pytest.mark.parametrize(
        "invalid_offset",
        [
            "invalid",
            "0400",  # Missing sign
            "+04",  # Too short
            "+04000",  # Too long
            "Z0400",  # Wrong sign character
            "+ab00",  # Non-numeric
        ],
    )
    def test_parse_timezone_offset_invalid(
        self, plugin: ActionModule, invalid_offset: str
    ) -> None:
        """Test that invalid offset strings raise ValueError."""
        with pytest.raises(ValueError, match="Invalid offset format"):
            plugin._parse_timezone_offset(invalid_offset)

    def test_get_target_timezone_success(
        self, monkeypatch: pytest.MonkeyPatch, plugin: ActionModule
    ) -> None:
        """Test successful timezone detection."""
        monkeypatch.setattr(
            plugin,
            "_cmd",
            lambda *_args, **_kwargs: {"rc": 0, "stdout": "-0500"},
        )

        tz = plugin._get_target_timezone({})
        expected = timezone(timedelta(hours=-5))
        assert tz == expected

    def test_get_target_timezone_command_failure(
        self, monkeypatch: pytest.MonkeyPatch, plugin: ActionModule
    ) -> None:
        """Test fallback to UTC when date command fails."""
        monkeypatch.setattr(
            plugin, "_cmd", lambda *_args, **_kwargs: {"rc": 1}
        )

        tz = plugin._get_target_timezone({})
        assert tz == timezone.utc

    def test_get_target_timezone_empty_output(
        self, monkeypatch: pytest.MonkeyPatch, plugin: ActionModule
    ) -> None:
        """Test fallback to UTC when date returns empty output."""
        monkeypatch.setattr(
            plugin, "_cmd", lambda *_args, **_kwargs: {"rc": 0, "stdout": ""}
        )

        tz = plugin._get_target_timezone({})
        assert tz == timezone.utc

    def test_get_target_timezone_invalid_format(
        self, monkeypatch: pytest.MonkeyPatch, plugin: ActionModule
    ) -> None:
        """Test fallback to UTC when offset format is invalid."""
        monkeypatch.setattr(
            plugin,
            "_cmd",
            lambda *_args, **_kwargs: {"rc": 0, "stdout": "invalid"},
        )

        tz = plugin._get_target_timezone({})
        assert tz == timezone.utc
