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

"""Tests for who module_utils."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils.who_utils import (
    parse_who,
)

JC_PATH = (
    "ansible_collections.o0_o.posix.plugins.module_utils.who_utils.jc_parse"
)


def test_parse_who_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_jc(parser: str, value: object) -> Dict[str, object]:
        assert parser == "who"
        return {
            "user": "alice",
            "line": "pts/0",
            "host": "10.0.0.1",
            "time": "2025-01-15 10:00",
            "pid": 1234,
        }

    monkeypatch.setattr(JC_PATH, fake_jc)

    result = parse_who(
        "ignored", now=datetime(2025, 1, 15, 11, 0, tzinfo=timezone.utc)
    )

    session = result["sessions"][0]
    assert session["user"] == "alice"
    assert session["tty"] == "pts/0"
    assert session["host"] == "10.0.0.1"
    assert session["pid"] == 1234
    assert session["login_at"]["iso8601"] == "2025-01-15T10:00:00Z"
    assert session["elapsed"]["seconds"] == 3600


def test_parse_who_list(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_jc(parser: str, value: object) -> List[Dict[str, object]]:
        assert parser == "who"
        return [
            {
                "user": "bob",
                "line": "pts/1",
                "host": "workstation",
                "time": "2025-01-15 09:30",
            },
            {
                "user": "charlie",
                "line": "pts/2",
                "time": "2025-01-15 09:45",
                "pid": 5678,
            },
        ]

    monkeypatch.setattr(JC_PATH, fake_jc)

    reference = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    result = parse_who("ignored", now=reference)

    assert result["sessions"][0]["user"] == "bob"
    assert result["sessions"][1]["pid"] == 5678
    assert result["sessions"][0]["elapsed"]["seconds"] == 1800


def test_parse_who_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(JC_PATH, lambda parser, value: [])

    with pytest.raises(ValueError, match="no session entries"):
        parse_who("ignored")


def test_parse_who_openbsd_partial_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test parsing OpenBSD who entries with month/day timestamps."""

    def fake_jc(parser: str, value: object) -> List[Dict[str, object]]:
        assert parser == "who"
        return [
            {
                "user": "root",
                "tty": "ttyC0",
                "time": "Oct 16 11:03",
            },
        ]

    monkeypatch.setattr(JC_PATH, fake_jc)

    reference = datetime(2025, 10, 20, 13, 39, 3, tzinfo=timezone.utc)
    result = parse_who("ignored", now=reference)

    session = result["sessions"][0]
    assert session["user"] == "root"
    assert session["tty"] == "ttyC0"
    assert session["login_at"]["iso8601"] == "2025-10-16T11:03:00Z"

    expected_login = datetime(2025, 10, 16, 11, 3, tzinfo=timezone.utc)
    assert session["elapsed"]["seconds"] == int(
        (reference - expected_login).total_seconds()
    )


def test_parse_who_openbsd_year_rollover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test year adjustment for OpenBSD who timestamps lacking year."""

    def fake_jc(parser: str, value: object) -> List[Dict[str, object]]:
        assert parser == "who"
        return [
            {
                "user": "root",
                "tty": "ttyp0",
                "time": "Dec 31 23:50",
            },
        ]

    monkeypatch.setattr(JC_PATH, fake_jc)

    reference = datetime(2026, 1, 2, 1, 0, tzinfo=timezone.utc)
    result = parse_who("ignored", now=reference)

    session = result["sessions"][0]
    assert session["tty"] == "ttyp0"
    assert session["login_at"]["iso8601"] == "2025-12-31T23:50:00Z"
