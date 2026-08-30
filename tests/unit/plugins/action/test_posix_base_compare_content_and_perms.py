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


@pytest.mark.parametrize(
    "old_stat, old_content, old_perms, content, perms, selinux, expect_change",
    [
        # No file exists: always changed
        ({"exists": False}, None, {}, "new text\n", {}, False, True),
        # File exists, content same, no perms: no change
        ({"exists": True}, "same\n", {}, "same\n", {}, False, False),
        # File exists, content differs: change
        ({"exists": True}, "old\n", {}, "new\n", {}, False, True),
        # Only the final newline differs, either direction: change.
        # Both sides split into the same one line, which is what the
        # comparison used to be blind to
        ({"exists": True}, "abc\n", {}, "abc", {}, False, True),
        ({"exists": True}, "abc", {}, "abc\n", {}, False, True),
        # Only trailing spaces on the last line differ: change
        ({"exists": True}, "abc  \n", {}, "abc\n", {}, False, True),
        # An empty destination against empty content: no change
        ({"exists": True}, "", {}, "", {}, False, False),
        # An empty destination against a bare newline: change
        ({"exists": True}, "", {}, "\n", {}, False, True),
        # A carriage return is what read cannot report, so content
        # carrying one still compares equal to the file read describes
        ({"exists": True}, "a\nb\n", {}, "a\r\nb\r\n", {}, False, False),
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
    monkeypatch,
    write_base,
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
    old_lines = old_content.splitlines() if old_content else []

    monkeypatch.setattr(
        write_base, "_pseudo_stat", lambda path, task_vars=None: old_stat
    )
    monkeypatch.setattr(
        write_base,
        "_read",
        lambda **kwargs: {
            "paths": {dest: {"content": old_content, "lines": old_lines}}
        },
    )
    monkeypatch.setattr(
        write_base,
        "_get_perms",
        lambda path, selinux=False, task_vars=None: old_perms,
    )

    if expect_change == "error":
        with pytest.raises(RuntimeError):
            write_base._compare_content_and_perms(
                content=content,
                dest=dest,
                perms=perms,
                selinux=selinux,
                task_vars={},
            )
    else:
        ret_changed, ret_content, ret_lines = (
            write_base._compare_content_and_perms(
                content=content,
                dest=dest,
                perms=perms,
                selinux=selinux,
                task_vars={},
            )
        )
        assert ret_changed is expect_change
        assert ret_content == old_content
        assert ret_lines == (old_content.splitlines() if old_content else [])
