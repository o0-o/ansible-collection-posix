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


@pytest.mark.parametrize(
    "exists,check_mode,should_create,expect_change",
    [
        (True, False, False, False),   # already exists
        (False, True, False, True),    # missing, check_mode
        (False, False, True, True),    # missing, real mkdir
    ]
)
def test_mk_dest_dir_behavior(
    monkeypatch, base, exists, check_mode, should_create, expect_change
):
    """
    Test _mk_dest_dir in normal conditions:
    - Directory exists => no change (changed not set or False)
    - Directory missing + check mode => change flagged
    - Directory missing + create => actually created
    """
    base._task.check_mode = check_mode
    base.results = {}

    file_path = "/tmp/some/deep/path/file.txt"
    dir_path = os.path.dirname(file_path)

    monkeypatch.setattr(
        base, "_pseudo_stat",
        lambda p, task_vars=None: {"exists": exists, "type": "directory" if exists else None}
    )

    if should_create:
        monkeypatch.setattr(
            base, "_mkdir",
            lambda p, task_vars=None: {"changed": True}
        )

    base._mk_dest_dir(file_path, task_vars={})

    if expect_change:
        assert base.results.get("changed") is True
    else:
        # We only assume changed will NOT be True, not necessarily set at all
        assert base.results.get("changed") is not True


def test_mk_dest_dir_mkdir_failure(monkeypatch, base):
    """
    Simulate a failure during directory creation and ensure the
    failure is captured in the results dict.
    """
    base._task.check_mode = False
    base.results = {}

    file_path = "/tmp/fail/path/file.txt"

    monkeypatch.setattr(
        base, "_pseudo_stat",
        lambda p, task_vars=None: {"exists": False}
    )

    def failing_mkdir(p, task_vars=None):
        raise OSError("simulated mkdir failure")

    monkeypatch.setattr(base, "_mkdir", failing_mkdir)

    base._mk_dest_dir(file_path, task_vars={})

    assert base.results['failed'] is True
    assert "Error creating" in base.results['msg']
    assert base.results['rc'] == 256
