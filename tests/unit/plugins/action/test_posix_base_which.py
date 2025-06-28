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

import pytest


@pytest.mark.parametrize(
    "binary, cmd_outputs, expected_result",
    [
        # command -v returns absolute path
        (
            "true",
            {
                ("sh", "-c", "command -v true"): {
                    "rc": 0,
                    "stdout": "/usr/bin/true"
                },
            },
            "/usr/bin/true"
        ),

        # command -v returns shell builtin
        (
            "echo",
            {
                ("sh", "-c", "command -v echo"): {
                    "rc": 0,
                    "stdout": "echo"
                },
            },
            "echo"
        ),

        # command -v fails, which succeeds with absolute path
        (
            "cat",
            {
                ("sh", "-c", "command -v cat"): {
                    "rc": 1,
                    "stdout": ""
                },
                ("which", "cat"): {
                    "rc": 0,
                    "stdout": "/bin/cat"
                },
            },
            "/bin/cat"
        ),

        # command -v fails, which returns shell builtin text
        (
            "printf",
            {
                ("sh", "-c", "command -v printf"): {
                    "rc": 1,
                    "stdout": ""
                },
                ("which", "printf"): {
                    "rc": 0,
                    "stdout": "printf: shell built-in command"
                },
            },
            "printf"
        ),

        # neither method finds it
        (
            "fakecmd",
            {
                ("sh", "-c", "command -v fakecmd"): {
                    "rc": 1,
                    "stdout": ""
                },
                ("which", "fakecmd"): {
                    "rc": 1,
                    "stdout": ""
                },
            },
            None
        ),
    ]
)
def test_which_logic(base, binary, cmd_outputs, expected_result):
    """
    Test PosixBase._which() behavior with mock _cmd output.
    """
    def mock_cmd(cmd, task_vars=None):
        return cmd_outputs.get(tuple(cmd), {"rc": 1, "stdout": ""})

    base._cmd = mock_cmd
    result = base._which(binary, task_vars={})
    assert result == expected_result
