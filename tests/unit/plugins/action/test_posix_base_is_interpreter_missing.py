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
    "result, expected",
    [
        # Positive: canary string appears in msg and rc is 127
        (
            {
                "rc": 127,
                "msg": (
                    "The module failed to execute correctly, you probably "
                    "need to set the interpreter for this host"
                ),
            },
            True,
        ),
        # Negative: rc is wrong or msg doesn't match
        (
            {
                "rc": 0,
                "msg": (
                    "The module failed to execute correctly, you probably "
                    "need to set the interpreter for this host"
                ),
            },
            False,
        ),
        ({"rc": 127, "msg": "unexpected failure message"}, False),
        (
            {
                "rc": 127,
            },
            False,
        ),
        ({}, False),
        ("not a dict", False),
    ],
)
def test_is_interpreter_missing_canary_only(base, result, expected) -> None:
    """
    Test _is_interpreter_missing detects Python errors by msg content.
    """
    assert base._is_interpreter_missing(result) is expected
