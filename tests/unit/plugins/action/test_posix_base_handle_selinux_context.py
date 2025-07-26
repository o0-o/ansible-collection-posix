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

import pytest
from ansible_collections.o0_o.posix.tests.utils import generate_temp_path
from ansible.errors import AnsibleActionFail


@pytest.mark.parametrize(
    "perms, which_map, expected_cmds, fail_cmd, expected_error",
    [
        # Full semanage + restorecon case
        (
            {"setype": "foo_t"},
            {
                "semanage": "/usr/sbin/semanage",
                "restorecon": "/sbin/restorecon",
                "chcon": "/usr/bin/chcon",
            },
            lambda dest: [
                ["semanage", "fcontext", "-a", "-t", "foo_t", dest],
                ["restorecon", dest],
            ],
            None,
            None,
        ),
        # chcon fallback only
        (
            {
                "seuser": "user_u",
                "serole": "object_r",
                "setype": "foo_t",
                "selevel": "s0",
            },
            {
                "semanage": None,
                "restorecon": None,
                "chcon": "/usr/bin/chcon",
            },
            lambda dest: [
                [
                    "chcon",
                    "-u", "user_u",
                    "-r", "object_r",
                    "-t", "foo_t",
                    "-l", "s0",
                    dest,
                ]
            ],
            None,
            None,
        ),
        # semanage fails
        (
            {"setype": "foo_t"},
            {
                "semanage": "/usr/sbin/semanage",
                "restorecon": "/sbin/restorecon",
                "chcon": "/usr/bin/chcon",
            },
            lambda dest: [
                ["semanage", "fcontext", "-a", "-t", "foo_t", dest]
            ],
            "semanage",
            "semanage",
        ),
        # restorecon fails
        (
            {"setype": "foo_t"},
            {
                "semanage": "/usr/sbin/semanage",
                "restorecon": "/sbin/restorecon",
                "chcon": "/usr/bin/chcon",
            },
            lambda dest: [
                ["semanage", "fcontext", "-a", "-t", "foo_t", dest],
                ["restorecon", dest],
            ],
            "restorecon",
            "restorecon",
        ),
        # chcon fails
        (
            {"seuser": "user_u"},
            {
                "semanage": None,
                "restorecon": None,
                "chcon": "/usr/bin/chcon",
            },
            lambda dest: [["chcon", "-u", "user_u", dest]],
            "chcon",
            "chcon",
        ),
    ]
)
def test_handle_selinux_context_logic(
    base, perms, which_map, expected_cmds, fail_cmd, expected_error
):
    """
    Unit test for _handle_selinux_context().
    Mocks _which() and _cmd() to simulate tool presence and command outcomes.
    """
    dest = generate_temp_path()
    issued_cmds = []

    # Mock _which to simulate tool presence
    base._which = lambda tool, task_vars=None: which_map.get(tool)

    # Mock _cmd to track and simulate execution
    def mock_cmd(cmd, task_vars=None):
        issued_cmds.append(cmd)
        if fail_cmd and fail_cmd in cmd[0]:
            return {"rc": 1, "stderr": f"{cmd[0]} failed"}
        return {"rc": 0, "stderr": ""}

    base._cmd = mock_cmd

    if expected_error:
        with pytest.raises(AnsibleActionFail, match=expected_error):
            base._handle_selinux_context(dest, perms)
    else:
        base._handle_selinux_context(dest, perms)

    assert issued_cmds == expected_cmds(dest)
