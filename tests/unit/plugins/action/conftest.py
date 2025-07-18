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
import tempfile
import pytest
from unittest.mock import MagicMock
from ansible_collections.o0_o.posix.plugins.action_utils import PosixBase
from ansible_collections.o0_o.posix.tests.utils import real_cmd


@pytest.fixture
def base():
    """
    Create a mocked PosixBase instance for unit testing with real command
    execution and isolated tmpdir for file operations.
    """
    # MagicMock action to override command execution
    action = MagicMock()

    # Create PosixBase instance with mocked dependencies
    base = PosixBase(
        task=MagicMock(),
        connection=MagicMock(),
        play_context=MagicMock(),
        loader=MagicMock(),
        templar=MagicMock(),
        shared_loader_obj=MagicMock(),
    )

    # Set action reference for internal use
    base._action = action

    # Patch connection shell helpers
    temp_dir = tempfile.mkdtemp(prefix="ansible_test_")
    base._connection._shell.tmpdir = temp_dir
    base._connection._shell.join_path = os.path.join
    base._connection._shell.quote = lambda s: f"'{s}'"

    # Replace _cmd and _low_level_execute_command with real_cmd
    base._cmd = real_cmd
    base._action._low_level_execute_command = real_cmd

    return base
