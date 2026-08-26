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


def _record_commands(monkeypatch, write_base) -> list:
    """Record every command issued and report success."""
    issued = []

    def mock_command(cmd, stdin=None, task_vars=None, **kwargs):
        issued.append({"cmd": cmd, "stdin": stdin, "kwargs": kwargs})
        return {"rc": 0}

    monkeypatch.setattr(write_base, "_command", mock_command)
    return issued


@pytest.mark.parametrize(
    "content, expected_stdin",
    [
        # A list of lines is POSIX text: the last line terminates too
        (["one", "two"], "one\ntwo\n"),
        # A string is a whole file and reaches tee exactly as given
        ("one\ntwo\n", "one\ntwo\n"),
        ("no trailing newline", "no trailing newline"),
    ],
)
def test_write_temp_file_stages_the_content_verbatim(
    monkeypatch, write_base, content, expected_stdin
) -> None:
    """Test the candidate holds the bytes the caller normalized."""
    tmpfile = os.path.join(write_base._connection._shell.tmpdir, "file.txt")
    issued = _record_commands(monkeypatch, write_base)

    result = write_base._write_temp_file(content, tmpfile, task_vars={})

    assert result["rc"] == 0
    assert len(issued) == 1
    assert issued[0]["cmd"] == ["tee", tmpfile]
    assert issued[0]["stdin"] == expected_stdin
    # The command action would otherwise terminate the stream itself,
    # which is the whole newline decision taken away from the caller
    assert issued[0]["kwargs"]["stdin_add_newline"] is False


def test_write_temp_file_leaves_an_unasked_mode_alone(
    monkeypatch, write_base
) -> None:
    """Test no mode is invented for the candidate.

    The candidate is what ``mv`` carries into place, so a mode applied
    here is a mode applied to the destination. Without one the file
    keeps what the host's umask gave it.
    """
    tmpfile = os.path.join(write_base._connection._shell.tmpdir, "file.txt")
    issued = _record_commands(monkeypatch, write_base)

    write_base._write_temp_file(["one"], tmpfile, task_vars={})

    assert [entry["cmd"][0] for entry in issued] == ["tee"]


def test_write_temp_file_applies_the_mode_it_is_given(
    monkeypatch, write_base
) -> None:
    """Test a mode is applied to the candidate before placement."""
    tmpfile = os.path.join(write_base._connection._shell.tmpdir, "file.txt")
    issued = _record_commands(monkeypatch, write_base)

    write_base._write_temp_file(["one"], tmpfile, mode="0640", task_vars={})

    assert [entry["cmd"] for entry in issued] == [
        ["tee", tmpfile],
        ["chmod", "0640", tmpfile],
    ]


def test_write_temp_file_failure(monkeypatch, write_base) -> None:
    """Test _write_temp_file raises error when tee command fails."""

    def mock_command(cmd, stdin=None, task_vars=None, **kwargs):
        return {"rc": 1, "stderr": "no tee"}

    monkeypatch.setattr(write_base, "_command", mock_command)

    with pytest.raises(
        RuntimeError, match=r"Failed to write temp file .*no tee"
    ):
        write_base._write_temp_file(["oops"], "/tmp/fail", task_vars={})


def test_write_temp_file_chmod_failure(monkeypatch, write_base) -> None:
    """Test a mode that cannot be applied fails before placement."""

    def mock_command(cmd, stdin=None, task_vars=None, **kwargs):
        if cmd[0] == "chmod":
            return {"rc": 1, "stderr": "no chmod"}
        return {"rc": 0}

    monkeypatch.setattr(write_base, "_command", mock_command)

    with pytest.raises(
        RuntimeError, match=r"Failed to chmod temp file: no chmod"
    ):
        write_base._write_temp_file(
            ["oops"], "/tmp/fail", mode="0640", task_vars={}
        )
