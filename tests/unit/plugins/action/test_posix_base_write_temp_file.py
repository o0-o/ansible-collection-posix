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

import os

import pytest

from ansible.errors import AnsibleActionFail


def test_write_temp_file_success(monkeypatch, base) -> None:
    """Test _write_temp_file writes content successfully."""
    tmpfile = os.path.join(base._connection._shell.tmpdir, "file.txt")
    written = {}

    def mock_cmd(cmd, task_vars=None, check_mode=False, **kwargs):
        # Expect ['tee', tmpfile] as cmd, and 'stdin' as a kwarg
        if cmd == ["chmod", "0600", tmpfile]:
            return {"rc": 0}
        elif cmd == ["tee", tmpfile]:
            written["path"] = tmpfile
            written["content"] = kwargs.get("stdin")
            return {"rc": 0}
        raise Exception(f"unexpected cmd: {cmd}")

    monkeypatch.setattr(base, "_cmd", mock_cmd)

    result = base._write_temp_file(["one", "two"], tmpfile, task_vars={})

    assert result["rc"] == 0
    assert written["path"] == tmpfile
    assert written["content"].splitlines() == ["one", "two"]


def test_write_temp_file_failure(monkeypatch, base) -> None:
    """Test _write_temp_file raises error when tee command fails."""
    def mock_cmd(cmd, task_vars=None, check_mode=False, **kwargs):
        return {"rc": 1, "stderr": "no tee"}

    monkeypatch.setattr(base, "_cmd", mock_cmd)

    with pytest.raises(AnsibleActionFail, match=r"Failed to write temp file .*no tee"):
        base._write_temp_file(["oops"], "/tmp/fail", task_vars={})
