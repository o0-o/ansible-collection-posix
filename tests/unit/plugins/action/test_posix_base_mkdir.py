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
from ansible_collections.o0_o.posix.tests.utils import (
    generate_temp_path,
    cleanup_path,
)


@pytest.mark.parametrize(
    "exists, is_dir, setup, expect_error, error_msg, changed",
    [
        # Directory doesn't exist → should be created
        (False, False, None, False, None, True),
        # Directory already exists → no change
        (True, True, None, False, None, False),
        # File exists at path → should raise error
        (True, False, None, True, "not a directory", None),
        # Permission denied on intermediate dir → should raise error
        (
            False,
            False,
            "restrictive_subdir",
            True,
            "Failed to create directory",
            None,
        ),
    ],
)
def test_mkdir_behavior(
    base, exists, is_dir, setup, expect_error, error_msg, changed
) -> None:
    """Test _mkdir behavior in various scenarios."""
    path = generate_temp_path()

    try:
        if setup == "restrictive_subdir":
            # Skip this test when running as root since root can bypass permissions
            if os.geteuid() == 0:
                pytest.skip("Permission restriction test skipped when running as root")

            # Create a subdirectory with no permissions
            os.makedirs(path, exist_ok=True)
            restricted = os.path.join(path, "no_access")
            os.makedirs(restricted, exist_ok=True)
            os.chmod(restricted, 0o000)

            try:
                with pytest.raises(AnsibleActionFail) as excinfo:
                    base._mkdir(os.path.join(restricted, "fail"))
                if error_msg:
                    assert error_msg in str(excinfo.value)
            finally:
                # Restore permissions to allow cleanup
                os.chmod(restricted, 0o700)
            return

        # Pre-create a file or directory if needed
        if exists:
            if is_dir:
                os.makedirs(path, exist_ok=True)
            else:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("conflict file")

        if expect_error:
            with pytest.raises(AnsibleActionFail) as excinfo:
                base._mkdir(path)
            if error_msg:
                assert error_msg in str(excinfo.value)
        else:
            result = base._mkdir(path)
            assert result["rc"] == 0
            assert result["changed"] is changed

    finally:
        cleanup_path(path)


def test_mkdir_invalid_mode(base) -> None:
    """Test _mkdir with invalid mode argument."""
    path = generate_temp_path()

    try:
        with pytest.raises(AnsibleActionFail) as excinfo:
            base._mkdir(path, mode="invalid")
        assert "Failed to create directory" in str(excinfo.value)
    finally:
        cleanup_path(path)
