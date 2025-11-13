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

"""Tests for timezone-related methods in PosixActionBase."""

from __future__ import annotations

from datetime import timedelta, timezone

import pytest


@pytest.mark.parametrize(
    "offset_str, expected_hours, expected_minutes",
    [
        ("+0000", 0, 0),  # UTC
        ("-0500", -5, 0),  # EST
        ("+0530", 5, 30),  # India
        ("-0800", -8, 0),  # PST
        ("+1000", 10, 0),  # AEST
        ("-0330", -3, -30),  # Newfoundland
    ],
)
def test_parse_timezone_offset_valid(
    base, offset_str, expected_hours, expected_minutes
) -> None:
    """Test _parse_timezone_offset with valid offset strings."""
    result = base._parse_timezone_offset(offset_str)

    expected_delta = timedelta(hours=expected_hours, minutes=expected_minutes)
    expected_tz = timezone(expected_delta)

    assert result == expected_tz
    assert result.utcoffset(None) == expected_tz.utcoffset(None)


@pytest.mark.parametrize(
    "invalid_offset",
    [
        "invalid",  # Not a valid format
        "+05",  # Too short
        "+05300",  # Too long
        "0500",  # Missing sign
        "+25:00",  # Contains colon
        "+99999",  # Wrong length
        "",  # Empty string
    ],
)
def test_parse_timezone_offset_invalid(base, invalid_offset) -> None:
    """Test _parse_timezone_offset raises ValueError for invalid
    input."""
    with pytest.raises(ValueError, match="Invalid offset format"):
        base._parse_timezone_offset(invalid_offset)


def test_get_target_timezone_from_o0_os_facts(monkeypatch, base) -> None:
    """Test _get_target_timezone uses o0_os facts when available."""
    task_vars = {
        "o0_os": {
            "time": {
                "zone": {"offset": "-0500"},
            }
        }
    }

    result = base._get_target_timezone(task_vars)

    expected = timezone(timedelta(hours=-5))
    assert result == expected


def test_get_target_timezone_from_ansible_facts(monkeypatch, base) -> None:
    """Test _get_target_timezone falls back to ansible_facts."""
    task_vars = {
        "ansible_facts": {
            "ansible_date_time": {"tz_offset": "+1000"},
        }
    }

    result = base._get_target_timezone(task_vars)

    expected = timezone(timedelta(hours=10))
    assert result == expected


def test_get_target_timezone_from_command(monkeypatch, base) -> None:
    """Test _get_target_timezone runs date command as fallback."""

    def mock_cmd(cmd, task_vars=None, check_mode=None):
        if cmd == ["date", "+%z"]:
            return {"rc": 0, "stdout": "-0800\n"}
        return {"rc": 1, "stdout": ""}

    monkeypatch.setattr(base, "_cmd", mock_cmd)

    result = base._get_target_timezone({})

    expected = timezone(timedelta(hours=-8))
    assert result == expected


def test_get_target_timezone_command_failure_uses_utc(
    monkeypatch, base
) -> None:
    """Test _get_target_timezone returns UTC when date command fails."""

    def mock_cmd(cmd, task_vars=None, check_mode=None):
        return {"rc": 1, "stdout": ""}

    monkeypatch.setattr(base, "_cmd", mock_cmd)
    monkeypatch.setattr(base, "_def_inventory_hostname", lambda tv: "testhost")

    result = base._get_target_timezone({})

    assert result == timezone.utc


def test_get_target_timezone_invalid_offset_in_facts(
    monkeypatch, base
) -> None:
    """Test _get_target_timezone handles invalid offset in facts."""
    task_vars = {
        "o0_os": {
            "time": {
                "zone": {"offset": "invalid"},
            }
        }
    }

    def mock_cmd(cmd, task_vars=None, check_mode=None):
        if cmd == ["date", "+%z"]:
            return {"rc": 0, "stdout": "-0500\n"}
        return {"rc": 1, "stdout": ""}

    monkeypatch.setattr(base, "_cmd", mock_cmd)

    result = base._get_target_timezone(task_vars)

    # Should fall back to command after invalid fact
    expected = timezone(timedelta(hours=-5))
    assert result == expected


def test_get_target_timezone_prefers_o0_os_over_ansible_facts(
    monkeypatch, base
) -> None:
    """Test _get_target_timezone prefers o0_os facts over
    ansible_facts."""
    task_vars = {
        "o0_os": {
            "time": {
                "zone": {"offset": "+0530"},
            }
        },
        "ansible_facts": {
            "ansible_date_time": {"tz_offset": "-0800"},
        },
    }

    result = base._get_target_timezone(task_vars)

    # Should use o0_os value, not ansible_facts
    expected = timezone(timedelta(hours=5, minutes=30))
    assert result == expected


def test_get_target_timezone_handles_empty_offset(monkeypatch, base) -> None:
    """Test _get_target_timezone handles empty offset string in
    facts."""
    task_vars = {
        "o0_os": {
            "time": {
                "zone": {"offset": "   "},  # Whitespace only
            }
        }
    }

    def mock_cmd(cmd, task_vars=None, check_mode=None):
        if cmd == ["date", "+%z"]:
            return {"rc": 0, "stdout": "+0000\n"}
        return {"rc": 1, "stdout": ""}

    monkeypatch.setattr(base, "_cmd", mock_cmd)

    result = base._get_target_timezone(task_vars)

    # Should fall back to command
    expected = timezone.utc
    assert result == expected


def test_get_target_timezone_handles_non_dict_facts(monkeypatch, base) -> None:
    """Test _get_target_timezone handles malformed task_vars."""
    task_vars = {
        "o0_os": "not a dict",  # Invalid type
        "ansible_facts": None,  # Invalid type
    }

    def mock_cmd(cmd, task_vars=None, check_mode=None):
        if cmd == ["date", "+%z"]:
            return {"rc": 0, "stdout": "+1000\n"}
        return {"rc": 1, "stdout": ""}

    monkeypatch.setattr(base, "_cmd", mock_cmd)

    result = base._get_target_timezone(task_vars)

    # Should fall back to command
    expected = timezone(timedelta(hours=10))
    assert result == expected
