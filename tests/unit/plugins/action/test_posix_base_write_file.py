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

import os
import pwd
import grp
import pytest
from ansible.errors import AnsibleError
from unittest.mock import MagicMock

from ansible_collections.o0_o.posix.tests.utils import (
    generate_temp_path,
    cleanup_path,
    check_path_mode,
    check_path_ownership,
)


def test_write_file_rejects_invalid_content(base):
    """
    Ensure _write_file raises AnsibleError for unsupported content types
    such as None, integers, or mixed-type lists.
    """
    path = generate_temp_path()
    try:
        for invalid in [None, 123, [object()], ["foo", object()]]:
            with pytest.raises(AnsibleError):
                base._write_file(content=invalid, dest=path, task_vars={})
    finally:
        cleanup_path(path)


def test_write_file_basic_write(base):
    """
    Test basic functionality of _write_file writing string content
    to a file and marking the operation as changed.
    """
    path = generate_temp_path()
    try:
        result = base._write_file(
            content="hello\nworld\n", dest=path, task_vars={}
        )
        assert result["changed"] is True
        assert result["rc"] == 0
        with open(path, encoding="utf-8") as f:
            assert f.read().splitlines() == ["hello", "world"]
    finally:
        cleanup_path(path)


def test_write_file_backup_and_validate(base):
    """
    Ensure _write_file triggers validation and creates a backup
    when content is changed and backup=True.
    """
    path = generate_temp_path()
    with open(path, "w") as f:
        f.write("existing")

    base._validate_file = lambda tmp, cmd, task_vars: None
    base._create_backup = lambda dest, task_vars: dest + ".bak"

    result = base._write_file(
        content="new",
        dest=path,
        task_vars={},
        validate_cmd="cat %s",
        backup=True
    )

    assert result["changed"] is True
    assert result["backup_file"].endswith(".bak")

    cleanup_path(path)
    cleanup_path(path + ".bak")


def test_write_file_check_mode_and_diff(base):
    """
    Test that check_mode=True avoids actual changes but sets changed=True
    and includes the correct diff content.
    """
    path = generate_temp_path()
    original = "old content\n"
    updated = "new content\n"
    try:
        with open(path, "w") as f:
            f.write(original)

        base._slurp = lambda path, task_vars=None: {
            "content": original,
            "content_lines": original.splitlines(),
        }

        result = base._write_file(
            content=updated,
            dest=path,
            task_vars={"diff": True},
            check_mode=True
        )

        assert result["changed"] is True
        assert "diff" in result
        assert result["diff"]["before"] == original
        assert result["diff"]["after"] == updated
        with open(path, encoding="utf-8") as f:
            assert f.read() == original
    finally:
        cleanup_path(path)


def test_write_file_applies_permissions(base):
    """
    Confirm that _write_file applies owner, group, and mode
    permissions correctly.
    """
    path = generate_temp_path()
    uid = os.getuid()
    gid = os.getgid()
    perms = {
        "owner": pwd.getpwuid(uid).pw_name,
        "group": grp.getgrgid(gid).gr_name,
        "mode": "0640"
    }
    try:
        result = base._write_file(
            content="secure",
            dest=path,
            perms=perms,
            task_vars={}
        )
        assert result["changed"] is True
        check_path_mode(path, perms)
        check_path_ownership(path, perms)
    finally:
        cleanup_path(path)


def test_write_file_selinux_tools_missing(base):
    """
    Ensure _write_file raises an error when SELinux setype is requested
    but required tools like 'chcon' are missing.
    """
    base._which = lambda name, task_vars=None: (
        None if name == "chcon" else "/usr/sbin/semanage"
    )
    base._display = MagicMock()
    dest = generate_temp_path()
    try:
        with pytest.raises(AnsibleError, match="requires 'chcon'"):
            base._write_file(
                content="foo",
                dest=dest,
                perms={"setype": "foo_t"},
                task_vars={}
            )
    finally:
        cleanup_path(dest)
