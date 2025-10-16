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

"""Tests for utilities provided by PosixActionBase."""

from __future__ import annotations

from typing import Dict, List

import pytest

try:
    from ansible_collections.o0_o.posix.plugins.module_utils.posix_action_base import (  # type: ignore  # noqa: E501
        PosixActionBase,
    )
except ModuleNotFoundError:  # pragma: no cover - ansible missing in tests
    PosixActionBase = None  # type: ignore

pytestmark = pytest.mark.skipif(
    PosixActionBase is None, reason="ansible package is required"
)


class _Recorder:
    """Capture debug output emitted via the display helper."""

    def __init__(self) -> None:
        self.messages: List[str] = []

    def vvv(self, message: str) -> None:
        self.messages.append(message)


class DummyPosixAction(PosixActionBase):
    """Minimal PosixActionBase subclass with stubbed _cmd behaviour."""

    def __init__(self, responses: List[Dict[str, object]]) -> None:
        self._responses = list(responses)
        self.calls: List[List[str]] = []
        self._display = _Recorder()

    def _cmd(  # type: ignore[override]
        self,
        cmd: List[str],
        task_vars=None,
        check_mode=None,
    ) -> Dict[str, object]:
        self.calls.append(cmd)
        if not self._responses:
            raise AssertionError("No more stubbed responses available")
        return self._responses.pop(0)


def test_which_prefers_command_v(monkeypatch) -> None:
    """command -v success returns the resolved path."""

    responses = [
        {"rc": 0, "stdout": "/usr/bin/grep\n"},
    ]
    dummy = DummyPosixAction(responses)

    result = dummy._which("grep")

    assert result == "/usr/bin/grep"
    assert dummy.calls[0] == ["sh", "-c", "command -v grep"]


def test_which_handles_builtin_via_command_v() -> None:
    """command -v with no slash indicates a shell builtin."""

    responses = [
        {"rc": 0, "stdout": "cd\n"},
    ]
    dummy = DummyPosixAction(responses)

    result = dummy._which("cd")

    assert result == "cd"


def test_which_fallback_returns_path_from_which() -> None:
    """Fallback to which returns the path reported by which."""

    responses = [
        {"rc": 1, "stdout": ""},
        {"rc": 0, "stdout": "/usr/bin/Grep\n"},
    ]
    dummy = DummyPosixAction(responses)

    result = dummy._which("Grep")

    assert result == "/usr/bin/grep"
    assert dummy.calls[1] == ["which", "Grep"]
    assert any(
        "command -v Grep failed" in msg for msg in dummy._display.messages
    )


def test_which_fallback_detects_builtin_message() -> None:
    """when which reports a builtin the command name is returned."""

    responses = [
        {"rc": 1, "stdout": ""},
        {
            "rc": 0,
            "stdout": "Grep: shell built-in command\n",
        },
    ]
    dummy = DummyPosixAction(responses)

    result = dummy._which("Grep")

    assert result == "Grep"


def test_which_debug_message_emitted() -> None:
    """command -v failure triggers debug log before fallback."""

    responses = [
        {"rc": 1, "stdout": ""},
        {"rc": 1, "stdout": ""},
    ]
    dummy = DummyPosixAction(responses)

    dummy._which("missing")

    assert any(
        "command -v missing failed" in msg for msg in dummy._display.messages
    )
