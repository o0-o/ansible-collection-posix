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


def test_write_file_check_mode_and_diff(monkeypatch, write_base) -> None:
    """Test _write_file check mode and diff functionality."""
    tmp_path = generate_temp_path()
    original = "old content\n"
    updated = "new content\n"
    try:
        with open(tmp_path, "w") as f:
            f.write(original)

        monkeypatch.setattr(
            write_base,
            "_read",
            lambda **kwargs: {
                "paths": {
                    tmp_path: {
                        "content": original,
                        "lines": original.splitlines(),
                    }
                }
            },
        )

        result = write_base._write_file(
            content=updated,
            dest=tmp_path,
            task_vars={"diff": True},
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
