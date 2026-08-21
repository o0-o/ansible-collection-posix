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
from unittest.mock import MagicMock

import grp
import os
import pwd

import pytest

from ansible_collections.o0_o.posix.tests.utils import (
    generate_temp_path,
    cleanup_path,
    check_path_mode,
    check_path_ownership,
    real_cmd,
)


def test_write_file_rejects_invalid_content(write_base) -> None:
    """Test _write_file rejects invalid content types."""
    tmp_path = generate_temp_path()
    try:
        for invalid in [None, 123, [object()], ["foo", object()]]:
            with pytest.raises(RuntimeError):
                write_base._write_file(
                    content=invalid, dest=tmp_path, task_vars={}
                )
    finally:
        cleanup_path(tmp_path)


def test_write_file_basic_write(write_base) -> None:
    """Test basic _write_file functionality."""
    tmp_path = generate_temp_path()
    try:
        result = write_base._write_file(
            content="hello\nworld\n", dest=tmp_path, task_vars={}
        )
        assert result["changed"] is True
        assert result["rc"] == 0
        with open(tmp_path, encoding="utf-8") as f:
            assert f.read().splitlines() == ["hello", "world"]
    finally:
        cleanup_path(tmp_path)


def test_write_file_backup_and_validate(monkeypatch, write_base) -> None:
    """Test _write_file backup and validation features."""
    tmp_path = generate_temp_path()
    with open(tmp_path, "w") as f:
        f.write("existing")

    monkeypatch.setattr(
        write_base, "_validate_file", lambda tmp, cmd, task_vars: None
    )
    monkeypatch.setattr(
        write_base, "_create_backup", lambda dest, task_vars: dest + ".bak"
    )

    # Mock _read to use real_cmd and cat to read the file
    def mock_read(paths, task_vars=None, **kwargs):
        result = real_cmd(f"cat '{paths}'")
        if result["rc"] != 0:
            return {"paths": {paths: {"content": "", "lines": []}}}
        content = result["stdout"]
        return {
            "paths": {
                paths: {
                    "content": content,
                    "lines": content.splitlines(),
                }
            }
        }

    monkeypatch.setattr(write_base, "_read", mock_read)

    result = write_base._write_file(
        content="new",
        dest=tmp_path,
        task_vars={},
        validate_cmd="cat %s",
        backup=True,
    )

    assert result["changed"] is True
    assert result["backup_file"].endswith(".bak")

    cleanup_path(tmp_path)
    cleanup_path(tmp_path + ".bak")


def _pin_read(monkeypatch, write_base, dest: str, content: str) -> None:
    """Report ``content`` as what the destination currently holds."""
    monkeypatch.setattr(
        write_base,
        "_read",
        lambda **kwargs: {
            "paths": {
                dest: {"content": content, "lines": content.splitlines()}
            }
        },
    )


def _honour_task_check_mode(monkeypatch, write_base) -> None:
    """Let the task's check mode reach the command seam.

    Production's ``_command`` delegates to the command action, which
    consults the task it was handed; the harness's stand-in only reads
    the explicit argument. Bridging the two is what makes a call that
    forgot to pin ``check_mode=False`` visible here.
    """
    passthrough = write_base._command

    def _command(cmd, check_mode=None, **kwargs):
        if check_mode is None:
            check_mode = write_base._task.check_mode
        return passthrough(cmd, check_mode=check_mode, **kwargs)

    monkeypatch.setattr(write_base, "_command", _command)


def test_write_file_check_mode_and_diff(monkeypatch, write_base) -> None:
    """Test check mode predicts the change and diffs it."""
    tmp_path = generate_temp_path()
    original = "old content\n"
    updated = "new content\n"
    try:
        with open(tmp_path, "w") as f:
            f.write(original)

        _pin_read(monkeypatch, write_base, tmp_path, original)
        write_base._task.diff = True

        result = write_base._write_file(
            content=updated,
            dest=tmp_path,
            task_vars={},
            check_mode=True,
        )

        assert result["changed"] is True
        assert "diff" in result
        assert result["diff"]["before"] == original
        assert result["diff"]["after"] == updated
        with open(tmp_path, encoding="utf-8") as f:
            assert f.read() == original
    finally:
        cleanup_path(tmp_path)


def test_write_file_diff_only_when_the_task_asks(
    monkeypatch, write_base
) -> None:
    """Test the diff follows the task's request, not a task var."""
    tmp_path = generate_temp_path()
    original = "old content\n"
    updated = "new content\n"
    try:
        with open(tmp_path, "w") as f:
            f.write(original)

        _pin_read(monkeypatch, write_base, tmp_path, original)
        write_base._task.diff = False

        result = write_base._write_file(
            content=updated,
            dest=tmp_path,
            # The key the diff was once gated on; Ansible never sets it
            task_vars={"diff": True},
            check_mode=True,
        )

        assert result["changed"] is True
        assert "diff" not in result
    finally:
        cleanup_path(tmp_path)


def test_write_file_check_mode_stages_and_validates(
    monkeypatch, write_base
) -> None:
    """Test check mode stages a real candidate and validates it.

    The candidate has to exist for the validation command to mean
    anything, so the witness the validator writes is the proof that it
    ran against the content that would have landed.
    """
    tmp_path = generate_temp_path()
    witness = generate_temp_path()
    original = "old content\n"
    updated = "new content\n"
    try:
        with open(tmp_path, "w") as f:
            f.write(original)

        _pin_read(monkeypatch, write_base, tmp_path, original)
        _honour_task_check_mode(monkeypatch, write_base)
        write_base._task.check_mode = True
        write_base._task.diff = False

        result = write_base._write_file(
            content=updated,
            dest=tmp_path,
            task_vars={},
            validate_cmd=f"cp %s {witness}",
            backup=True,
            check_mode=True,
        )

        assert result["changed"] is True
        with open(witness, encoding="utf-8") as f:
            assert f.read().splitlines() == updated.splitlines()
        with open(tmp_path, encoding="utf-8") as f:
            assert f.read() == original
        # Neither the candidate nor a backup survives the prediction
        tmpdir = write_base._connection._shell.tmpdir
        assert os.listdir(tmpdir) == []
        assert "backup_file" not in result
    finally:
        cleanup_path(tmp_path)
        cleanup_path(witness)


def test_write_file_check_mode_refuses_an_invalid_candidate(
    monkeypatch, write_base
) -> None:
    """Test a validation failure fails the task in check mode too."""
    tmp_path = generate_temp_path()
    try:
        with open(tmp_path, "w") as f:
            f.write("old content\n")

        _pin_read(monkeypatch, write_base, tmp_path, "old content\n")
        _honour_task_check_mode(monkeypatch, write_base)
        write_base._task.check_mode = True
        write_base._task.diff = False

        with pytest.raises(RuntimeError, match="Validation failed"):
            write_base._write_file(
                content="new content\n",
                dest=tmp_path,
                task_vars={},
                validate_cmd="false %s",
                check_mode=True,
            )
    finally:
        cleanup_path(tmp_path)


def test_write_file_check_mode_creates_its_scratch_space(
    monkeypatch, write_base
) -> None:
    """Test check mode makes the scratch directory it stages into."""
    tmp_path = generate_temp_path()
    fixture_tmpdir = write_base._connection._shell.tmpdir
    try:
        with open(tmp_path, "w") as f:
            f.write("old content\n")

        _pin_read(monkeypatch, write_base, tmp_path, "old content\n")
        _honour_task_check_mode(monkeypatch, write_base)
        write_base._task.check_mode = True
        write_base._task.diff = False
        # No scratch directory yet, so mktemp has to run for real
        write_base._connection._shell.tmpdir = None

        result = write_base._write_file(
            content="new content\n",
            dest=tmp_path,
            task_vars={},
            check_mode=True,
        )

        staged = write_base._connection._shell.tmpdir
        assert result["changed"] is True
        assert staged and os.path.isdir(staged)
        assert os.listdir(staged) == []
    finally:
        staged = write_base._connection._shell.tmpdir
        if staged and staged != fixture_tmpdir:
            cleanup_path(staged)
        write_base._connection._shell.tmpdir = fixture_tmpdir
        cleanup_path(tmp_path)


def test_write_file_applies_permissions(write_base) -> None:
    """Test _write_file applies permissions correctly."""
    tmp_path = generate_temp_path()
    uid = os.getuid()
    gid = os.getgid()
    perms = {
        "owner": pwd.getpwuid(uid).pw_name,
        "group": grp.getgrgid(gid).gr_name,
        "mode": "0640",
    }
    try:
        result = write_base._write_file(
            content="secure", dest=tmp_path, perms=perms, task_vars={}
        )
        assert result["changed"] is True
        check_path_mode(tmp_path, perms)
        check_path_ownership(tmp_path, perms)
    finally:
        cleanup_path(tmp_path)


def test_write_file_selinux_tools_missing(monkeypatch, write_base) -> None:
    """Test _write_file error when SELinux tools missing."""
    monkeypatch.setattr(
        write_base,
        "_which",
        lambda name, task_vars=None: (
            None if name == "chcon" else "/usr/sbin/semanage"
        ),
    )
    write_base._display = MagicMock()
    tmp_path = generate_temp_path()
    try:
        with pytest.raises(RuntimeError, match="requires 'chcon'"):
            write_base._write_file(
                content="foo",
                dest=tmp_path,
                perms={"setype": "foo_t"},
                task_vars={},
            )
    finally:
        cleanup_path(tmp_path)
