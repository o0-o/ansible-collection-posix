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

import pytest


@pytest.mark.parametrize(
    "binary, cmd_outputs, expected_result",
    [
        # command -v returns absolute path
        (
            "true",
            [
                {"rc": 0, "stdout": "/usr/bin/true"},  # command -v
            ],
            "/usr/bin/true",
        ),
        # command -v returns shell builtin (no slash in output)
        (
            "echo",
            [
                {"rc": 0, "stdout": "echo"},  # command -v
            ],
            "echo",
        ),
        # command -v fails, which succeeds with absolute path
        (
            "cat",
            [
                {"rc": 1, "stdout": ""},  # command -v fails
                {"rc": 0, "stdout": "/bin/cat"},  # which succeeds
            ],
            "/bin/cat",
        ),
        # command -v fails, which returns shell builtin text
        (
            "printf",
            [
                {"rc": 1, "stdout": ""},  # command -v fails
                {"rc": 0, "stdout": "printf: shell built-in command"},  # which
            ],
            "printf",
        ),
        # neither method finds it
        (
            "fakecmd",
            [
                {"rc": 1, "stdout": ""},  # command -v fails
                {"rc": 1, "stdout": ""},  # which fails
            ],
            None,
        ),
    ],
)
def test_which_logic(monkeypatch, base, binary, cmd_outputs, expected_result):
    """Test PosixBase._which() behavior with various command outputs."""
    call_count = [0]

    def mock_command(cmd, task_vars=None, **kwargs):
        idx = call_count[0]
        call_count[0] += 1
        if idx < len(cmd_outputs):
            return cmd_outputs[idx]
        return {"rc": 1, "stdout": ""}

    monkeypatch.setattr(base, "_command", mock_command)
    result = base._which(binary, task_vars={})
    assert result == expected_result
