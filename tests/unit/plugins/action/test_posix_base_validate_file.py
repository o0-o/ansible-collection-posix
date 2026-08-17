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


def test_validate_file_noop_for_none(write_base) -> None:
    """Test _validate_file no-op when validate_cmd is None."""
    write_base._validate_file("/tmp/somefile", None)


def test_validate_file_noop_for_empty_string(write_base) -> None:
    """Test _validate_file no-op when validate_cmd is empty."""
    write_base._validate_file("/tmp/somefile", "")


def test_validate_file_success(monkeypatch, write_base) -> None:
    """Test _validate_file successful validation."""
    called = {}

    def mock_command(cmd, task_vars=None, **kwargs):
        called["cmd"] = cmd
        return {"rc": 0}

    write_base._command = mock_command

    write_base._validate_file("/tmp/foo.conf", "validate %s")

    assert called["cmd"] == "validate '/tmp/foo.conf'"


def test_validate_file_failure_raises(monkeypatch, write_base) -> None:
    """Test _validate_file raises error on validation failure."""

    def mock_command(cmd, task_vars=None, **kwargs):
        return {"rc": 1, "stderr": "syntax error"}

    write_base._command = mock_command

    with pytest.raises(RuntimeError, match="Validation failed:"):
        write_base._validate_file("/etc/foo", "validate %s")
