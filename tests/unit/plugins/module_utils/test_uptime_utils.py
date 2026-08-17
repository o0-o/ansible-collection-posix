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

"""Tests for uptime module_utils."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


import pytest

from ansible_collections.o0_o.posix.plugins.module_utils.uptime_utils import (
    parse_uptime,
)

JC_PATH = (
    "ansible_collections.o0_o.posix.plugins.module_utils.uptime_utils.jc_parse"
)


@pytest.fixture(name="reference")
def fixture_reference_time() -> datetime:
    return datetime(2025, 1, 15, 15, 41, 26, tzinfo=timezone.utc)


def test_parse_uptime_linux(
    monkeypatch: pytest.MonkeyPatch, reference: datetime
) -> None:
    seconds = 3 * 86400 + 2 * 3600 + 3 * 60

    def fake_jc(parser: str, value: object) -> dict[str, object]:
        assert parser == "uptime"
        return {
            "uptime_seconds": seconds,
            "load": [0.81, 0.72, 0.69],
            "up_since": "2025-01-12T13:38:26.123456+00:00",
            "users": 2,
        }

    monkeypatch.setattr(JC_PATH, fake_jc)

    result = parse_uptime("ignored", now=reference)

    assert result["uptime"]["elapsed"]["seconds"] == seconds
    assert result["load"] == {"1m": 0.81, "5m": 0.72, "15m": 0.69}
    assert result["login_sessions"] == 2
    expected_start = datetime(2025, 1, 12, 13, 38, 26, tzinfo=timezone.utc)
    started = result["uptime"]["started"]
    assert started["seconds"] == int(expected_start.timestamp())
    assert "microseconds" not in started


def test_parse_uptime_bsd(
    monkeypatch: pytest.MonkeyPatch, reference: datetime
) -> None:
    seconds = 10 * 86400 + 4 * 3600 + 23 * 60

    def fake_jc(parser: str, value: object) -> list[dict[str, object]]:
        assert parser == "uptime"
        return [
            {
                "uptime_seconds": seconds,
                "load_average": ["0.59", "0.60", "0.52"],
            }
        ]

    monkeypatch.setattr(JC_PATH, fake_jc)

    result = parse_uptime("ignored", now=reference)

    assert result["uptime"]["elapsed"]["seconds"] == seconds
    assert result["load"] == {"1m": 0.59, "5m": 0.60, "15m": 0.52}
    assert result["login_sessions"] == 0


def test_parse_uptime_minutes(
    monkeypatch: pytest.MonkeyPatch, reference: datetime
) -> None:
    def fake_jc(parser: str, value: object) -> dict[str, object]:
        assert parser == "uptime"
        return {
            "uptime": "5 mins",
            "load_1m": 0.01,
            "load_5m": 0.05,
            "load_15m": 0.10,
            "users": "1",
        }

    monkeypatch.setattr(JC_PATH, fake_jc)

    result = parse_uptime("ignored", now=reference)

    assert result["uptime"]["elapsed"]["seconds"] == 5 * 60
    assert result["load"]["1m"] == 0.01
    assert result["load"]["15m"] == 0.10

    expected_start = reference - timedelta(seconds=5 * 60)
    assert result["uptime"]["started"]["seconds"] == int(
        expected_start.timestamp()
    )
    assert result["login_sessions"] == 1
