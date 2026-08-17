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
import shutil
import tempfile
from typing import Any, Optional, Union
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


class _RealCommandMixin:
    """Override _command at class level to run commands for real.

    Overriding the seam on the class instead of assigning it on the
    instance keeps the stub honest: the signature must keep matching
    production's, and if production ever renames ``_command`` this
    override goes dead and the renamed method runs against the mocked
    Ansible plumbing instead of quietly passing.
    """

    def _command(
        self,
        cmd: Union[str, list[str]],
        stdin: Optional[str] = None,
        chdir: Optional[str] = None,
        task_vars: Optional[dict[str, Any]] = None,
        check_mode: Optional[bool] = None,
        strip: bool = True,
        raw: Optional[Union[bool, str]] = None,
    ) -> dict[str, Any]:
        """Run cmd through real_cmd instead of the command action."""
        return real_cmd(
            cmd,
            stdin=stdin,
            chdir=chdir,
            task_vars=task_vars,
            check_mode=check_mode,
            strip=strip,
            raw=raw,
        )


class TestPosixActionBase(_RealCommandMixin, PosixActionBase, ActionBase):
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


class TestReadPosixActionBase(
    _RealCommandMixin, ReadPosixActionBase, ActionBase
):
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


class TestWritePosixActionBase(
    _RealCommandMixin, WritePosixActionBase, ActionBase
):
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


def _make_base(cls: type) -> tuple[Any, str]:
    """Build a base test instance with mocked Ansible dependencies.

    Command execution is real: the class supplies a ``_command``
    override delegating to real_cmd. An isolated temporary directory
    stands in for the connection shell's tmpdir; the caller owns its
    removal.

    :param type cls: Test subclass to instantiate
    :returns tuple: The configured instance and its temporary directory
    """
    instance = cls(
        task=MagicMock(),
        connection=MagicMock(),
        play_context=MagicMock(),
        loader=MagicMock(),
        templar=MagicMock(),
        shared_loader_obj=MagicMock(),
    )

    # Add display mock
    instance._display = MagicMock()

    # Initialize inventory_hostname (normally set by action plugin)
    instance.inventory_hostname = "localhost"

    # Patch connection shell helpers
    temp_dir = tempfile.mkdtemp(prefix="ansible_test_")
    instance._connection._shell = MagicMock()
    instance._connection._shell.tmpdir = temp_dir
    instance._connection._shell.join_path = os.path.join
    instance._connection._shell.quote = lambda s: f"'{s}'"

    return instance, temp_dir


@pytest.fixture
def base():
    """Create a TestPosixActionBase instance for unit testing.

    Provides a TestPosixActionBase instance with mocked Ansible
    dependencies but real command execution capabilities for
    integration-style testing. Creates an isolated temporary directory
    for file operations and removes it on teardown.

    :returns: Configured TestPosixActionBase instance with mocked
              dependencies

    .. note::
       This fixture uses real command execution via real_cmd for
       testing actual POSIX command behavior.
    """
    instance, temp_dir = _make_base(TestPosixActionBase)
    try:
        yield instance
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def read_base():
    """Create a TestReadPosixActionBase instance for unit testing.

    Provides a TestReadPosixActionBase instance with mocked Ansible
    dependencies but real command execution capabilities for
    integration-style testing. Creates an isolated temporary directory
    for file operations and removes it on teardown.

    :returns: Configured TestReadPosixActionBase instance with mocked
              dependencies

    .. note::
       This fixture uses real command execution via real_cmd for
       testing actual POSIX command behavior. Use this for testing
       methods from ReadPosixActionBase like _cat, _read, _stat.
    """
    instance, temp_dir = _make_base(TestReadPosixActionBase)
    try:
        yield instance
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def write_base():
    """Create a TestWritePosixActionBase instance for unit testing.

    Provides a TestWritePosixActionBase instance with mocked Ansible
    dependencies but real command execution capabilities for
    integration-style testing. Creates an isolated temporary directory
    for file operations and removes it on teardown.

    :returns: Configured TestWritePosixActionBase instance with mocked
              dependencies

    .. note::
       This fixture uses real command execution via real_cmd for
       testing actual POSIX command behavior. Use this for testing
       methods from WritePosixActionBase like _write_file, _mkdir,
       _pseudo_stat.
    """
    instance, temp_dir = _make_base(TestWritePosixActionBase)
    try:
        yield instance
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
