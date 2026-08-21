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

"""Unit tests for the read action plugin's argument processing."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ansible.errors import AnsibleActionFail
from ansible_collections.o0_o.posix.plugins.action.read import ActionModule


@pytest.fixture
def plugin() -> ActionModule:
    """Create a read ActionModule with mocked Ansible plumbing."""

    task = MagicMock()
    task.async_val = 0
    task.check_mode = False
    task.diff = False
    task.args = {}

    action = ActionModule(
        task=task,
        connection=MagicMock(),
        play_context=MagicMock(),
        loader=MagicMock(),
        templar=MagicMock(),
        shared_loader_obj=MagicMock(),
    )
    action._display = MagicMock()
    action.inventory_hostname = "localhost"

    return action


def test_empty_paths_rejected(plugin) -> None:
    """Test an empty paths list fails before any host work.

    The argument spec's required=True is satisfied by the key, so
    nothing but this check stands between an accidentally empty list
    and a result that reports no paths as though none were asked for.
    """

    plugin._task.args = {"paths": []}

    with pytest.raises(
        AnsibleActionFail, match="paths must contain at least one path"
    ):
        plugin._def_args()


def test_a_path_is_accepted(plugin) -> None:
    """Test the rejection reaches no further than an empty list."""

    plugin._task.args = {"path": "/etc/hosts"}

    plugin._def_args()

    assert plugin.paths == ["/etc/hosts"]
