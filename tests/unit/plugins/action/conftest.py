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
import tempfile
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils import PosixActionBase
from ansible_collections.o0_o.posix.tests.utils import real_cmd
from ansible.plugins.action import ActionBase


class TestPosixActionBase(PosixActionBase, ActionBase):
    """Test class that combines PosixActionBase mixin with
    ActionBase.
    """

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Dummy run method for testing."""
        return {"changed": False}


@pytest.fixture
def base():
    """Create a TestPosixActionBase instance for unit testing.

    Provides a TestPosixActionBase instance with mocked Ansible
    dependencies
    but real command execution capabilities for integration-style
    testing. Creates an isolated temporary directory for file
    operations.

    :returns: Configured TestPosixActionBase instance with mocked
              dependencies

    .. note::
       This fixture uses real command execution via real_cmd for
       testing actual POSIX command behavior.
    """
    # MagicMock action to override command execution
    action = MagicMock()

    # Create TestPosixActionBase instance with mocked dependencies
    base = TestPosixActionBase(
        task=MagicMock(),
        connection=MagicMock(),
        play_context=MagicMock(),
        loader=MagicMock(),
        templar=MagicMock(),
        shared_loader_obj=MagicMock(),
    )

    # Set action reference for internal use
    base._action = action

    # Add display mock
    base._display = MagicMock()

    # Patch connection shell helpers
    temp_dir = tempfile.mkdtemp(prefix="ansible_test_")
    base._connection._shell = MagicMock()
    base._connection._shell.tmpdir = temp_dir
    base._connection._shell.join_path = os.path.join
    base._connection._shell.quote = lambda s: f"'{s}'"

    # Replace _cmd and _low_level_execute_command with real_cmd
    base._cmd = real_cmd
    base._action._low_level_execute_command = real_cmd

    return base
