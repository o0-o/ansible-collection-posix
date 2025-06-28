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
from unittest.mock import MagicMock
from ansible.errors import AnsibleError


from ansible_collections.o0_o.posix.tests.utils import (
    generate_temp_path,
    cleanup_path,
    check_path_mode,
    check_path_ownership,
)


@pytest.mark.parametrize("content", [
    None,
    123,
    {"foo": "bar"},
    object(),
])
def test_write_file_invalid_content_strings(base, content):
    """Reject content that is not str or list of str/numbers."""
    path = generate_temp_path()
    try:
        with pytest.raises(
            AnsibleError, match="requires a string or list of strings"
        ):
            base._write_file(content=content, dest=path, task_vars={})
    finally:
        cleanup_path(path)


@pytest.mark.parametrize("content", [
    [object()],
    ['foo', object()],
    [lambda x: x],
    [{"key": "val"}],
])
def test_write_file_reject_invalid_content_lists(base, content):
    """Reject content lists with incompatible types."""
    path = generate_temp_path()
    try:
        with pytest.raises(
            AnsibleError, match="requires strings or numbers"
        ):
            base._write_file(content=content, dest=path, task_vars={})
    finally:
        cleanup_path(path)


@pytest.mark.parametrize(
    "content, set_perms, backup, validate_cmd, expect_backup, "
    "expect_validate",
    [
        (["foo", "bar"], False, False, None, False, False),
        (["mixed", 12, 3.45], False, False, None, False, False),
        ("bar\nbaz", True, False, None, False, False),
        ("backup me", False, True, None, True, False),
        (["validate me"], False, False, "cat %s", False, True),
    ]
)
def test_write_file_variants(
    base, content, set_perms, backup, validate_cmd,
    expect_backup, expect_validate
):
    """Test _write_file() for feature combinations and handlers."""
    path = generate_temp_path()
    called = {"validate": False, "backup": False}

    if set_perms:
        uid = os.getuid()
        gid = os.getgid()
        user = pwd.getpwuid(uid).pw_name
        group = grp.getgrgid(gid).gr_name
        perms = {"owner": user, "group": group, "mode": "0640"}
    else:
        perms = None

    def mock_validate_file(tmpfile, validate_cmd_arg, task_vars=None):
        called["validate"] = True
        assert validate_cmd_arg == validate_cmd
        assert os.path.exists(tmpfile)

    def mock_create_backup(dest_path, task_vars=None):
        called["backup"] = True
        return f"{dest_path}.bak"

    base._validate_file = mock_validate_file
    base._create_backup = mock_create_backup

    try:
        result = base._write_file(
            content=content,
            dest=path,
            task_vars={},
            perms=perms,
            backup=backup,
            validate_cmd=validate_cmd
        )

        expected_lines = (
            content.splitlines()
            if isinstance(content, str)
            else list(map(str, content))
        )
        with open(path, "r", encoding="utf-8") as f:
            written = f.read().splitlines()
        assert written == expected_lines

        assert result["changed"] is True
        assert result["rc"] == 0
        assert "msg" in result
        assert called["validate"] is expect_validate
        assert called["backup"] is expect_backup
        if expect_backup:
            assert "backup_file" in result

        if perms:
            check_path_mode(path, perms)
            check_path_ownership(path, perms)

    finally:
        cleanup_path(path)


@pytest.mark.parametrize(
    "which_map, expected_error, expect_warning, expect_handler_call",
    [
        (
            {"chcon": None, "semanage": None},
            "both 'chcon' and 'semanage' are missing",
            False,
            False,
        ),
        (
            {"chcon": None, "semanage": "/usr/sbin/semanage"},
            "requires 'chcon' to apply contexts",
            False,
            False,
        ),
        (
            {"chcon": "/usr/bin/chcon", "semanage": None},
            None,
            True,
            True,
        ),
        (
            {"chcon": "/usr/bin/chcon", "semanage": "/usr/sbin/semanage"},
            None,
            False,
            True,
        ),
    ]
)
def test_selinux_tool_availability(
    base, which_map, expected_error,
    expect_warning, expect_handler_call
):
    """Test SELinux tool logic inside _write_file()."""
    base._display = MagicMock()
    base._display.warning = MagicMock()

    dest = generate_temp_path()
    perms = {"setype": "foo_t"}
    base._which = lambda cmd, task_vars=None: which_map.get(cmd)
    base._handle_selinux_context = MagicMock()

    try:
        if expected_error:
            with pytest.raises(AnsibleError, match=expected_error):
                base._write_file(
                    content="foo", dest=dest, task_vars={}, perms=perms
                )
            base._handle_selinux_context.assert_not_called()
        else:
            base._write_file(
                content="bar", dest=dest, task_vars={}, perms=perms
            )

            if expect_warning:
                base._display.warning.assert_called_once()
                assert "semanage is not" in (
                    base._display.warning.call_args[0][0]
                )
            else:
                base._display.warning.assert_not_called()

            if expect_handler_call:
                base._handle_selinux_context.assert_called_once()
            else:
                base._handle_selinux_context.assert_not_called()
    finally:
        cleanup_path(dest)


@pytest.mark.parametrize(
    "test_case, perms, tmp_mode, sub_mode, fail_subdir, "
    "expected_error, force_dest",
    [
        (
            "temp_write_fail",
            None,
            0o600,
            0o700,
            True,
            "Failed to write temp file",
            None,
        ),
        (
            "mv_fail",
            None,
            0o700,
            0o500,
            True,
            "Failed to move temp file into place",
            None,
        ),
        (
            "chown_fail",
            {"owner": "nonexistentuser"},
            0o700,
            0o700,
            False,
            "Failed to chown",
            None,
        ),
        (
            "chgrp_fail",
            {"group": "nonexistentgroup"},
            0o700,
            0o700,
            False,
            "Failed to chgrp",
            None,
        ),
        (
            "mv_over_dev_null",
            None,
            0o700,
            0o700,
            False,
            "Failed to move temp file into place",
            "/dev/null",
        ),
        (
            "success",
            {"mode": "0400"},
            0o700,
            0o700,
            False,
            None,
            None,
        ),
    ]
)
def test_write_file_error_cases(
    base, test_case, perms, tmp_mode, sub_mode,
    fail_subdir, expected_error, force_dest
):
    """
    Parametrized test for failure conditions in _write_file.
    """
    tmpdir = generate_temp_path()
    subdir = os.path.join(tmpdir, "sub")
    dest = force_dest or os.path.join(subdir, "dest.txt")

    try:
        os.mkdir(tmpdir, mode=0o700)
        os.mkdir(subdir, mode=sub_mode)
        os.chmod(tmpdir, tmp_mode)

        base._connection._shell.tmpdir = tmpdir

        if expected_error:
            with pytest.raises(AnsibleError, match=expected_error):
                base._write_file(
                    content=["foo"],
                    dest=dest,
                    task_vars={},
                    perms=perms,
                )
        else:
            result = base._write_file(
                content=["bar"],
                dest=dest,
                task_vars={},
                perms=perms,
            )
            assert result["changed"] is True
            assert result["rc"] == 0
            assert "msg" in result
            assert os.path.exists(dest)
            with open(dest, encoding="utf-8") as f:
                assert f.read().strip() == "bar"
    finally:
        if not force_dest:
            cleanup_path(tmpdir)
