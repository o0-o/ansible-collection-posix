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
from ansible.errors import AnsibleActionFail


def test_validate_file_noop_for_none(base):
    """
    Ensure _validate_file() is a no-op when validate_cmd is None.

    This allows skipping validation when no command is given.
    """
    base._validate_file("/tmp/somefile", None)


def test_validate_file_noop_for_empty_string(base):
    """
    Ensure _validate_file() is a no-op when validate_cmd is an empty string.

    Validation should not run for empty command input.
    """
    base._validate_file("/tmp/somefile", "")


def test_validate_file_success(monkeypatch, base):
    """
    Simulate a successful validation command.

    Ensures that _validate_file runs the expected shell command when
    a validation command is provided and the return code is 0.
    """
    called = {}

    def mock_cmd(argv, task_vars=None):
        called["cmd"] = argv
        return {"rc": 0}

    def mock_quote(s):
        return f"'{s}'"

    base._cmd = mock_cmd
    base._quote = mock_quote

    base._validate_file("/tmp/foo.conf", "validate %s")

    assert called["cmd"] == "validate '/tmp/foo.conf'"


def test_validate_file_failure_raises(monkeypatch, base):
    """
    Simulate a failed validation command.

    Ensures that _validate_file raises an AnsibleActionFail when the validation
    command fails (non-zero return code).
    """
    def mock_cmd(argv, task_vars=None):
        return {"rc": 1, "stderr": "syntax error"}

    base._cmd = mock_cmd
    base._quote = lambda s: s  # No quoting for this test

    with pytest.raises(AnsibleActionFail, match="Validation failed:"):
        base._validate_file("/etc/foo", "validate %s")
