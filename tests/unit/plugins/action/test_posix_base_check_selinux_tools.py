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
from ansible.errors import AnsibleActionFail


def test_selinux_not_requested(base):
    """
    If no SELinux parameters are provided, the method should return False.
    """
    result = base._check_selinux_tools(perms={}, task_vars={})
    assert result is False


def test_selinux_tools_missing_both(base, monkeypatch):
    """
    If both chcon and semanage are missing, an error should be raised.
    """
    monkeypatch.setattr(
        base, "_which", lambda tool, task_vars=None: None
    )

    with pytest.raises(AnsibleActionFail, match="both 'chcon' and 'semanage'"):
        base._check_selinux_tools(
            perms={"setype": "something"},
            task_vars={},
        )


def test_selinux_chcon_missing_only(base, monkeypatch):
    """
    If chcon is missing but semanage is present, an error should be raised.
    """
    def fake_which(tool, task_vars=None):
        return "/usr/sbin/semanage" if tool == "semanage" else None

    monkeypatch.setattr(base, "_which", fake_which)

    with pytest.raises(AnsibleActionFail, match="requires 'chcon'"):
        base._check_selinux_tools(
            perms={"setype": "something"},
            task_vars={},
        )


def test_selinux_semanage_missing_warns(base, monkeypatch):
    """
    If semanage is missing but chcon is present, a warning should be issued.
    """
    monkeypatch.setattr(
        base,
        "_which",
        lambda tool, task_vars=None: "/bin/chcon"
        if tool == "chcon" else None
    )

    warnings = []

    class FakeDisplay:
        def warning(self, msg):
            warnings.append(msg)

        def vvv(self, msg):
            pass

    base._display = FakeDisplay()

    result = base._check_selinux_tools(
        perms={"serole": "some_role"},
        task_vars={},
    )

    assert result is True
    assert any("chcon is available but semanage is not" in w for w in warnings)


def test_selinux_both_tools_present(base, monkeypatch):
    """
    If both chcon and semanage are found, method should return True.
    """
    monkeypatch.setattr(
        base,
        "_which",
        lambda tool, task_vars=None: f"/usr/sbin/{tool}"
    )

    logs = []

    class FakeDisplay:
        def warning(self, msg):
            raise AssertionError("Unexpected warning")

        def vvv(self, msg):
            logs.append(msg)

    base._display = FakeDisplay()

    result = base._check_selinux_tools(
        perms={"seuser": "system_u"},
        task_vars={},
    )

    assert result is True
    assert any("SELinux check: chcon=" in line for line in logs)
