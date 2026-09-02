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

from ansible_collections.o0_o.posix.plugins.module_utils.command_utils import (
    is_interpreter_missing,
)


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
def test_is_interpreter_missing_canary_only(result, expected) -> None:
    """Test is_interpreter_missing detects Python errors by msg content."""
    assert is_interpreter_missing(result) is expected


def test_a_present_interpreter_that_cannot_run_is_missing() -> None:
    """The xcode-select stub is an absent interpreter, whatever it exits.

    Stock macOS ships /usr/bin/python3 as a stub that prints an install
    prompt and exits 1, so interpreter discovery accepts the path and
    the payload never runs. The fallback used to watch only for 127,
    which the stub never gives, and the raw lane's Darwin guest could
    not pass. The stub's own words are the canary.
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.command_utils import (  # noqa: E501
        is_interpreter_missing,
    )

    stub = {
        "rc": 1,
        "msg": (
            "Module result deserialization failed: No start of json char found"
        ),
        "module_stdout": (
            "xcode-select: note: No developer tools were found, "
            "requesting install.\n"
        ),
        "module_stderr": "Shared connection to 192.168.64.25 closed.\r\n",
    }
    assert is_interpreter_missing(stub) is True

    # A module that merely crashed with rc 1 and a traceback is not an
    # interpreter problem, and stays one the caller has to read
    crashed = {
        "rc": 1,
        "msg": "MODULE FAILURE",
        "module_stderr": "Traceback (most recent call last): ...",
    }
    assert is_interpreter_missing(crashed) is False
