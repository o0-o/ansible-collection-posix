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
import pytest
from ansible.errors import AnsibleError


@pytest.mark.parametrize("file_type, flag, expected_type, is_symlink", [
    ("file", "-f", "file", False),
    ("directory", "-d", "directory", False),
    ("symlink", "-L", "file", True),  # symlink to a file
])
def test_pseudo_stat_detects_type(
    base, tmp_path, file_type, flag, expected_type, is_symlink
):
    """
    Verify that _pseudo_stat correctly detects common POSIX types:
    regular file, directory, and symlink.
    Also verifies symlink tracking for symlinked paths.
    """
    # Create appropriate test file
    target = tmp_path / f"test_{file_type}"
    if file_type == "file":
        target.write_text("sample content")
    elif file_type == "directory":
        target.mkdir()
    elif file_type == "symlink":
        real = tmp_path / "real_file"
        real.write_text("data")
        target.symlink_to(real)

    result = base._pseudo_stat(str(target))

    assert result["exists"] is True
    assert result["type"] == expected_type
    assert result["is_symlink"] is is_symlink


def test_pseudo_stat_nonexistent(base):
    """
    Verify that _pseudo_stat correctly reports a non-existent file.
    """
    fake_path = "/tmp/this/path/should/not/exist"
    result = base._pseudo_stat(fake_path)
    assert result["exists"] is False
    assert result["type"] is None


def test_pseudo_stat_unsupported_type(base, tmp_path):
    """
    Verify that _pseudo_stat raises an error if the file exists
    but matches none of the expected POSIX types.
    """
    # Make a named pipe (FIFO) and test it
    fifo_path = tmp_path / "fifo"
    os.mkfifo(fifo_path)

    # Remove all type detection logic from this test by patching _cmd
    # to always return rc=1 after test -e
    def fake_cmd(args, task_vars=None, check_mode=None):
        if args == ["test", "-e", str(fifo_path)]:
            return {"rc": 0, "raw": False}
        return {"rc": 1, "raw": False}

    base._cmd = fake_cmd

    with pytest.raises(AnsibleError, match="All POSIX 'test' commands failed"):
        base._pseudo_stat(str(fifo_path))
