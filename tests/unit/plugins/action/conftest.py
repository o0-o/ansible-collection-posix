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
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils import (
    PosixActionBase,
    ReadPosixActionBase,
)
from ansible_collections.o0_o.posix.tests.utils import real_cmd
from ansible.plugins.action import ActionBase

try:
    from ansible_collections.o0_o.posix.plugins.module_utils.write_posix_action_base import (  # noqa: E501
        WritePosixActionBase,
    )
except ImportError:
    WritePosixActionBase = None  # type: ignore


class TestPosixActionBase(PosixActionBase, ActionBase):
    """Test class that combines PosixActionBase mixin with
    ActionBase.
    """

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Dummy run method for testing."""
        return {"changed": False}


class TestReadPosixActionBase(ReadPosixActionBase, ActionBase):
    """Test class that combines ReadPosixActionBase mixin with
    ActionBase.
    """

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Dummy run method for testing."""
        return {"changed": False}


class TestWritePosixActionBase(WritePosixActionBase, ActionBase):
    """Test class that combines WritePosixActionBase mixin with
    ActionBase.
    """

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
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

    # Initialize inventory_hostname (normally set by action plugin)
    base.inventory_hostname = "localhost"

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


@pytest.fixture
def read_base():
    """Create a TestReadPosixActionBase instance for unit testing.

    Provides a TestReadPosixActionBase instance with mocked Ansible
    dependencies but real command execution capabilities for
    integration-style testing. Creates an isolated temporary directory
    for file operations.

    :returns: Configured TestReadPosixActionBase instance with mocked
              dependencies

    .. note::
       This fixture uses real command execution via real_cmd for
       testing actual POSIX command behavior. Use this for testing
       methods from ReadPosixActionBase like _cat, _read, _stat.
    """
    # MagicMock action to override command execution
    action = MagicMock()

    # Create TestReadPosixActionBase instance with mocked dependencies
    read_base = TestReadPosixActionBase(
        task=MagicMock(),
        connection=MagicMock(),
        play_context=MagicMock(),
        loader=MagicMock(),
        templar=MagicMock(),
        shared_loader_obj=MagicMock(),
    )

    # Set action reference for internal use
    read_base._action = action

    # Add display mock
    read_base._display = MagicMock()

    # Initialize inventory_hostname (normally set by action plugin)
    read_base.inventory_hostname = "localhost"

    # Patch connection shell helpers
    temp_dir = tempfile.mkdtemp(prefix="ansible_test_")
    read_base._connection._shell = MagicMock()
    read_base._connection._shell.tmpdir = temp_dir
    read_base._connection._shell.join_path = os.path.join
    read_base._connection._shell.quote = lambda s: f"'{s}'"

    # Replace _cmd and _low_level_execute_command with real_cmd
    read_base._cmd = real_cmd
    read_base._action._low_level_execute_command = real_cmd

    return read_base


@pytest.fixture
def write_base():
    """Create a TestWritePosixActionBase instance for unit testing.

    Provides a TestWritePosixActionBase instance with mocked Ansible
    dependencies but real command execution capabilities for
    integration-style testing. Creates an isolated temporary directory
    for file operations.

    :returns: Configured TestWritePosixActionBase instance with mocked
              dependencies

    .. note::
       This fixture uses real command execution via real_cmd for
       testing actual POSIX command behavior. Use this for testing
       methods from WritePosixActionBase like _write_file, _mkdir,
       _pseudo_stat.
    """
    # MagicMock action to override command execution
    action = MagicMock()

    # Create TestWritePosixActionBase instance with mocked dependencies
    write_base = TestWritePosixActionBase(
        task=MagicMock(),
        connection=MagicMock(),
        play_context=MagicMock(),
        loader=MagicMock(),
        templar=MagicMock(),
        shared_loader_obj=MagicMock(),
    )

    # Set action reference for internal use
    write_base._action = action

    # Add display mock
    write_base._display = MagicMock()

    # Initialize inventory_hostname (normally set by action plugin)
    write_base.inventory_hostname = "localhost"

    # Patch connection shell helpers
    temp_dir = tempfile.mkdtemp(prefix="ansible_test_")
    write_base._connection._shell = MagicMock()
    write_base._connection._shell.tmpdir = temp_dir
    write_base._connection._shell.join_path = os.path.join
    write_base._connection._shell.quote = lambda s: f"'{s}'"

    # Replace _cmd and _low_level_execute_command with real_cmd
    write_base._cmd = real_cmd
    write_base._action._low_level_execute_command = real_cmd

    return write_base
