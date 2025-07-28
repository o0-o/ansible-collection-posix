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


def test_selinux_not_requested(base) -> None:
    """
    Test _check_selinux_tools returns False when SELinux not requested.
    """
    result = base._check_selinux_tools(perms={}, task_vars={})
    assert result is False


def test_selinux_tools_missing_both(base, monkeypatch) -> None:
    """
    Test _check_selinux_tools raises error when both tools missing.
    """
    monkeypatch.setattr(base, "_which", lambda tool, task_vars=None: None)

    with pytest.raises(AnsibleActionFail, match="both 'chcon' and 'semanage'"):
        base._check_selinux_tools(
            perms={"setype": "something"},
            task_vars={},
        )


def test_selinux_chcon_missing_only(base, monkeypatch) -> None:
    """Test _check_selinux_tools raises error when chcon missing."""

    def fake_which(tool, task_vars=None):
        return "/usr/sbin/semanage" if tool == "semanage" else None

    monkeypatch.setattr(base, "_which", fake_which)

    with pytest.raises(AnsibleActionFail, match="requires 'chcon'"):
        base._check_selinux_tools(
            perms={"setype": "something"},
            task_vars={},
        )


def test_selinux_semanage_missing_warns(base, monkeypatch) -> None:
    """Test _check_selinux_tools warns when semanage missing."""
    monkeypatch.setattr(
        base,
        "_which",
        lambda tool, task_vars=None: "/bin/chcon" if tool == "chcon" else None,
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


def test_selinux_both_tools_present(base, monkeypatch) -> None:
    """Test _check_selinux_tools succeeds when both tools present."""
    monkeypatch.setattr(
        base, "_which", lambda tool, task_vars=None: f"/usr/sbin/{tool}"
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
