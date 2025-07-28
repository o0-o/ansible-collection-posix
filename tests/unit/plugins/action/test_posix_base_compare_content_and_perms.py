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

import pytest

from ansible.errors import AnsibleActionFail


@pytest.mark.parametrize(
    "old_stat, old_content, old_perms, content, perms, selinux, expect_change",
    [
        # No file exists: always changed
        ({"exists": False}, None, {}, "new text\n", {}, False, True),
        # File exists, content same, no perms: no change
        ({"exists": True}, "same\n", {}, "same\n", {}, False, False),
        # File exists, content differs: change
        ({"exists": True}, "old\n", {}, "new\n", {}, False, True),
        # File exists, perms differ: change
        (
            {"exists": True},
            "same\n",
            {"owner": "bob"},
            "same\n",
            {"owner": "alice"},
            False,
            True,
        ),
        # File exists, mode differs: change
        (
            {"exists": True},
            "same\n",
            {"mode": "rw-r--r--"},
            "same\n",
            {"mode": "0700"},
            False,
            True,
        ),
        # File exists, mode same: no change
        (
            {"exists": True},
            "same\n",
            {"mode": "rw-r--r--"},
            "same\n",
            {"mode": "0644"},
            False,
            False,
        ),
        # Invalid mode format
        (
            {"exists": True},
            "same\n",
            {"mode": "rw-r--r--"},
            "same\n",
            {"mode": "bad"},
            False,
            "error",
        ),
        # SELinux type differs → change
        (
            {"exists": True},
            "same\n",
            {"setype": "etc_t"},
            "same\n",
            {"setype": "bin_t"},
            True,
            True,
        ),
        # SELinux role differs → change
        (
            {"exists": True},
            "same\n",
            {"serole": "object_r"},
            "same\n",
            {"serole": "system_r"},
            True,
            True,
        ),
        # SELinux fully matches → no change
        (
            {"exists": True},
            "same\n",
            {
                "seuser": "system_u",
                "serole": "object_r",
                "setype": "etc_t",
                "selevel": "s0",
            },
            "same\n",
            {
                "seuser": "system_u",
                "serole": "object_r",
                "setype": "etc_t",
                "selevel": "s0",
            },
            True,
            False,
        ),
    ],
)
def test_compare_content_and_perms(
    base,
    old_stat,
    old_content,
    old_perms,
    content,
    perms,
    selinux,
    expect_change,
) -> None:
    """Test _compare_content_and_perms logic."""
    dest = "/tmp/testfile"

    base._pseudo_stat = lambda path, task_vars=None: old_stat
    base._slurp = lambda path, task_vars=None: {
        "content": old_content,
        "content_lines": old_content.splitlines() if old_content else [],
    }
    base._get_perms = lambda path, selinux=False, task_vars=None: old_perms

    if expect_change == "error":
        with pytest.raises(AnsibleActionFail):
            base._compare_content_and_perms(
                lines=content.splitlines(),
                dest=dest,
                perms=perms,
                selinux=selinux,
                task_vars={},
            )
    else:
        ret_changed, ret_content, ret_lines = base._compare_content_and_perms(
            lines=content.splitlines(),
            dest=dest,
            perms=perms,
            selinux=selinux,
            task_vars={},
        )
        assert ret_changed is expect_change
        assert ret_content == old_content
        assert ret_lines == (old_content.splitlines() if old_content else [])
