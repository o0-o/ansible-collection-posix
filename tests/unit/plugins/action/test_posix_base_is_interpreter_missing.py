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
    "result, expected",
    [
        # Positive cases: rc=127 and relevant stderr messages
        ({'rc': 127, 'module_stderr': 'python: command not found'}, True),
        ({'rc': 127, 'module_stderr': 'no such file or directory'}, True),
        ({'rc': 127, 'module_stderr': 'bad interpreter'}, True),
        ({'rc': 127, 'module_stderr': "can't open"}, True),

        # Negative cases: rc is not 127 or stderr doesn't match
        ({'rc': 0, 'module_stderr': 'python: command not found'}, False),
        ({'rc': 1, 'module_stderr': 'bad interpreter'}, False),
        ({'rc': 127, 'module_stderr': 'unexpected error'}, False),
        ({'rc': 127, 'module_stderr': ''}, False),
        ({'rc': 127}, False),
        ({}, False),
        ('not a dict', False),  # malformed input
    ]
)
def test_is_interpreter_missing_variants(base, result, expected):
    """
    Test interpreter detection logic with various result dicts.
    """
    assert base._is_interpreter_missing(result) is expected
