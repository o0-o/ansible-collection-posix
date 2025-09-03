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

import pytest

from ansible.errors import AnsibleActionFail


@pytest.mark.parametrize(
    "file_exists, cp_success, expect_error",
    [
        (False, True, False),  # File does not exist, returns None
        (True, True, False),  # File exists, cp succeeds, returns path
        (True, False, True),  # File exists, cp fails, error
    ],
)
def test_create_backup_behavior(
    base, file_exists, cp_success, expect_error
) -> None:
    """
    Test _create_backup handles existence, success, and error cases.
    """
    dest_path = "/tmp/testfile.txt"

    base._cmd = MagicMock(
        side_effect=[
            {"rc": 0} if file_exists else {"rc": 1},
            {"rc": 0} if cp_success else {"rc": 1, "stderr": "cp failed"},
        ]
    )
    base._generate_ansible_backup_path = MagicMock(
        return_value="/tmp/testfile.txt.fakebackup"
    )

    if expect_error:
        with pytest.raises(AnsibleActionFail, match="Backup failed"):
            base._create_backup(dest_path)
    else:
        result = base._create_backup(dest_path)
        if file_exists:
            assert result == "/tmp/testfile.txt.fakebackup"
        else:
            assert result is None


def test_generate_ansible_backup_path_format(base) -> None:
    """Test backup path generation format."""
    path = "/etc/hosts"
    backup_path = base._generate_ansible_backup_path(path)

    assert backup_path.startswith(path + ".")
    parts = backup_path.split(".")
    assert len(parts) >= 3  # path, md5, timestamp
    assert parts[-1].isdigit()
