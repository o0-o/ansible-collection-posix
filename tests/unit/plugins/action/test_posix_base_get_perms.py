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
    "cmd_output, selinux, expected",
    [
        (
            {
                "rc": 0,
                "stdout_lines": [
                    "-rw-r--r-- 1 user group 123 Jul 1 00:00 file"
                ],
                "stdout": "",
            },
            False,
            {"mode": "rw-r--r--", "owner": "user", "group": "group"},
        ),
        (
            {
                "rc": 0,
                "stdout_lines": [
                    (
                        "user_u:object_r:etc_t:s0 -rw-r--r-- user group 123 "
                        "Jul 1 00:00 file"
                    )
                ],
                "stdout": "",
            },
            True,
            {
                "mode": "rw-r--r--",
                "owner": "user",
                "group": "group",
                "seuser": "user_u",
                "serole": "object_r",
                "setype": "etc_t",
                "selevel": "s0",
            },
        ),
        (
            {
                "rc": 0,
                "stdout_lines": [
                    "-rw-r--r--+ 1 user group 123 Jul 1 00:00 file"
                ],
                "stdout": "",
            },
            False,
            {"mode": "rw-r--r--", "owner": "user", "group": "group"},
        ),
    ],
)
def test_get_perms_valid(
    monkeypatch, write_base, cmd_output, selinux, expected
) -> None:
    """Test _get_perms parses POSIX and SELinux output correctly."""
    monkeypatch.setattr(
        write_base, "_command", lambda *args, **kwargs: cmd_output
    )
    result = write_base._get_perms("/fake/file", selinux=selinux)
    assert result == expected


def test_get_perms_fails_on_error(monkeypatch, write_base) -> None:
    """
    Test _get_perms raises RuntimeError when ls command fails.
    """
    monkeypatch.setattr(
        write_base,
        "_command",
        lambda *args, **kwargs: {
            "rc": 1,
            "stderr": "ls: cannot access",
        },
    )

    with pytest.raises(RuntimeError, match="Could not stat"):
        write_base._get_perms("/fake/file", selinux=False)


def test_get_perms_raises_on_malformed_selinux_output(
    monkeypatch, write_base
) -> None:
    """Test _get_perms raises on malformed SELinux output."""
    monkeypatch.setattr(
        write_base,
        "_command",
        lambda *args, **kwargs: {
            "rc": 0,
            "stdout": "badselinux -rw-r--r-- user group",
            "stdout_lines": ["badselinux -rw-r--r-- user group"],
        },
    )

    with pytest.raises(RuntimeError, match="Unexpected SELinux output"):
        write_base._get_perms("/fake/file", selinux=True)
