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

"""Unit tests for the fstab filter plugin."""

from __future__ import annotations

from typing import Any, Dict, List, Union
from unittest.mock import MagicMock

import pytest

from ansible_collections.o0_o.posix.plugins.filter.fstab import FilterModule
from ansible_collections.o0_o.posix.tests.utils import find_mount_by_target


@pytest.fixture
def filter_module() -> FilterModule:
    """Create FilterModule instance for testing."""
    return FilterModule()


@pytest.fixture
def mock_parse_command(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock the parse_command method."""
    mock = MagicMock()
    monkeypatch.setattr(FilterModule, "parse_command", mock)
    return mock


def test_fstab_basic(
    filter_module: FilterModule, mock_parse_command: MagicMock
) -> None:
    """Test basic fstab parsing without facts format."""
    parsed_data = [
        {
            "fs_spec": "/dev/sda1",
            "fs_file": "/",
            "fs_vfstype": "ext4",
            "fs_mntops": "defaults",
            "fs_freq": 0,
            "fs_passno": 1,
        },
        {
            "fs_spec": "/dev/sda2",
            "fs_file": "/home",
            "fs_vfstype": "ext4",
            "fs_mntops": "defaults,noatime",
            "fs_freq": 0,
            "fs_passno": 2,
        },
    ]
    mock_parse_command.return_value = parsed_data

    # Test with string input
    fstab_content = """
/dev/sda1   /       ext4    defaults        0   1
/dev/sda2   /home   ext4    defaults,noatime   0   2
"""
    result = filter_module.fstab(fstab_content)

    # Verify parse_command was called
    mock_parse_command.assert_called_once_with(fstab_content, "fstab")
    assert result == parsed_data


def test_fstab_with_facts_format(
    filter_module: FilterModule, mock_parse_command: MagicMock
) -> None:
    """Test fstab parsing with facts=True format."""
    parsed_data = [
        {
            "fs_spec": "/dev/sda1",
            "fs_file": "/",
            "fs_vfstype": "ext4",
            "fs_mntops": "defaults",
            "fs_freq": 0,
            "fs_passno": 1,
        },
        {
            "fs_spec": "UUID=abc123",
            "fs_file": "/boot",
            "fs_vfstype": "ext2",
            "fs_mntops": "defaults,ro",
            "fs_freq": 1,
            "fs_passno": 2,
        },
        {
            "fs_spec": "tmpfs",
            "fs_file": "/tmp",
            "fs_vfstype": "tmpfs",
            "fs_mntops": "defaults,nodev,nosuid",
            "fs_freq": 0,
            "fs_passno": 0,
        },
    ]
    mock_parse_command.return_value = parsed_data

    result = filter_module.fstab("dummy_content", facts=True)

    expected = [
            {
                "target": "/",
                "source": "/dev/sda1",
                "driver": "ext4",
                "type": "regular",
                "fuse": False,
                "options": {"defaults": True},
                "dump": {"enabled": False},
                "fsck": {"enabled": True, "pass": 1},
            },
            {
                "target": "/boot",
                "source": "UUID=abc123",
                "driver": "ext2",
                "type": "regular",
                "fuse": False,
                "options": {"defaults": True, "ro": True},
                "dump": {"enabled": True, "days": 1},
                "fsck": {"enabled": True, "pass": 2},
            },
            {
                "target": "/tmp",
                "source": None,
                "driver": "tmpfs",
                "type": "virtual",
                "fuse": False,
                "options": {"defaults": True, "nodev": True, "nosuid": True},
                "dump": {"enabled": False},
                "fsck": {"enabled": False},
            },
    ]

    assert result == expected


def test_fstab_with_comments_and_blank_lines(
    filter_module: FilterModule, mock_parse_command: MagicMock
) -> None:
    """Test fstab parsing with comments and blank lines."""
    parsed_data = [
        {
            "fs_spec": "/dev/sda1",
            "fs_file": "/",
            "fs_vfstype": "ext4",
            "fs_mntops": "defaults",
            "fs_freq": 0,
            "fs_passno": 1,
        }
    ]
    mock_parse_command.return_value = parsed_data

    fstab_content = """
# /etc/fstab: static file system information
#
# <file system> <mount point>   <type>  <options>       <dump>  <pass>

/dev/sda1       /               ext4    defaults        0       1

# This is a comment
"""
    result = filter_module.fstab(fstab_content)
    assert result == parsed_data


def test_fstab_normalize_to_mount_format(filter_module: FilterModule) -> None:
    """Test normalization of fstab entries to mount format."""
    fstab_entries = [
        {
            "fs_spec": "/dev/sda1",
            "fs_file": "/",
            "fs_vfstype": "ext4",
            "fs_mntops": "defaults,noatime",
            "fs_freq": 0,
            "fs_passno": 1,
        },
        {
            "fs_spec": "nfs-server:/export",
            "fs_file": "/mnt/nfs",
            "fs_vfstype": "nfs",
            "fs_mntops": "rw,hard,intr",
            "fs_freq": 0,
            "fs_passno": 0,
        },
    ]

    result = filter_module._normalize_to_mount_format(fstab_entries)

    expected = [
        {
            "source": "/dev/sda1",
            "target": "/",
            "driver": "ext4",
            "options": ["defaults", "noatime"],
            "dump": 0,
            "pass": 1,
        },
        {
            "source": "nfs-server:/export",
            "target": "/mnt/nfs",
            "driver": "nfs",
            "options": ["rw", "hard", "intr"],
            "dump": 0,
            "pass": 0,
        },
    ]

    assert result == expected


def test_fstab_with_swap(
    filter_module: FilterModule, mock_parse_command: MagicMock
) -> None:
    """Test fstab parsing with swap entries."""
    parsed_data = [
        {
            "fs_spec": "/dev/sda3",
            "fs_file": "none",
            "fs_vfstype": "swap",
            "fs_mntops": "sw",
            "fs_freq": 0,
            "fs_passno": 0,
        }
    ]
    mock_parse_command.return_value = parsed_data

    result = filter_module.fstab("dummy", facts=True)

    expected = [
            {
                "target": "swap",
                "source": "/dev/sda3",
                "type": "paging",  # swap is paging type
                # No driver key since swap isn't a filesystem
                "fuse": False,
                "options": {"sw": True},
                "dump": {"enabled": False},
                "fsck": {"enabled": False},
            }
    ]

    assert result == expected


def test_fstab_with_bind_mount(
    filter_module: FilterModule, mock_parse_command: MagicMock
) -> None:
    """Test fstab parsing with bind mount entries."""
    parsed_data = [
        {
            "fs_spec": "/olddir",
            "fs_file": "/newdir",
            "fs_vfstype": "none",
            "fs_mntops": "bind",
            "fs_freq": 0,
            "fs_passno": 0,
        }
    ]
    mock_parse_command.return_value = parsed_data

    result = filter_module.fstab("dummy", facts=True)

    expected = [
            {
                "target": "/newdir",
                "source": "/olddir",
                "driver": "none",
                "type": "overlay",  # bind mounts are overlay type
                "fuse": False,
                "options": {"bind": True},
                "dump": {"enabled": False},
                "fsck": {"enabled": False},
            }
    ]

    assert result == expected


def test_fstab_with_invalid_dump_pass_values(
    filter_module: FilterModule, mock_parse_command: MagicMock
) -> None:
    """Test fstab parsing with invalid dump/pass values."""
    parsed_data = [
        {
            "fs_spec": "/dev/sda1",
            "fs_file": "/",
            "fs_vfstype": "ext4",
            "fs_mntops": "defaults",
            "fs_freq": -1,  # Invalid dump value
            "fs_passno": -1,  # Invalid pass value (but treated as disabled)
        },
        {
            "fs_spec": "/dev/sda2",
            "fs_file": "/home",
            "fs_vfstype": "ext4",
            "fs_mntops": "defaults",
            "fs_freq": "auto",  # Non-integer dump value
            "fs_passno": "auto",  # Non-integer pass value
        },
    ]
    mock_parse_command.return_value = parsed_data

    result = filter_module.fstab("dummy", facts=True)

    expected = [
            {
                "target": "/",
                "source": "/dev/sda1",
                "driver": "ext4",
                "type": "regular",
                "fuse": False,
                "options": {"defaults": True},
                "dump": {"invalid": -1},
                "fsck": {"invalid": -1, "enabled": False},
            },
            {
                "target": "/home",
                "source": "/dev/sda2",
                "driver": "ext4",
                "type": "regular",
                "fuse": False,
                "options": {"defaults": True},
                "dump": {"invalid": "auto"},
                "fsck": {"invalid": "auto"},
            },
    ]

    assert result == expected


@pytest.mark.parametrize(
    "input_type,input_data",
    [
        ("string", "/dev/sda1 / ext4 defaults 0 1"),
        ("list", ["/dev/sda1 / ext4 defaults 0 1"]),
        (
            "dict",
            {
                "stdout": "/dev/sda1 / ext4 defaults 0 1",
                "rc": 0,
            },
        ),
    ],
)
def test_fstab_input_types(
    filter_module: FilterModule,
    mock_parse_command: MagicMock,
    input_type: str,
    input_data: Union[str, List[str], Dict[str, Any]],
) -> None:
    """Test fstab filter with different input types."""
    parsed_data = [
        {
            "fs_spec": "/dev/sda1",
            "fs_file": "/",
            "fs_vfstype": "ext4",
            "fs_mntops": "defaults",
            "fs_freq": 0,
            "fs_passno": 1,
        }
    ]
    mock_parse_command.return_value = parsed_data

    result = filter_module.fstab(input_data)

    mock_parse_command.assert_called_once_with(input_data, "fstab")
    assert result == parsed_data


def test_fstab_empty_input(
    filter_module: FilterModule, mock_parse_command: MagicMock
) -> None:
    """Test fstab filter with empty input."""
    mock_parse_command.return_value = []

    result = filter_module.fstab("", facts=True)

    assert result == []


def test_fstab_with_fuse_filesystem(
    filter_module: FilterModule, mock_parse_command: MagicMock
) -> None:
    """Test fstab parsing with FUSE filesystems."""
    parsed_data = [
        {
            "fs_spec": "sshfs#user@host:/path",
            "fs_file": "/mnt/ssh",
            "fs_vfstype": "fuse.sshfs",
            "fs_mntops": "defaults",
            "fs_freq": 0,
            "fs_passno": 0,
        },
        {
            "fs_spec": "encfs#/encrypted",
            "fs_file": "/decrypted",
            "fs_vfstype": "fuse.encfs",
            "fs_mntops": "defaults",
            "fs_freq": 0,
            "fs_passno": 0,
        },
    ]
    mock_parse_command.return_value = parsed_data

    result = filter_module.fstab("dummy", facts=True)

    expected = [
            {
                "target": "/mnt/ssh",
                "source": "sshfs#user@host:/path",
                "driver": "fuse.sshfs",
                "type": "network",  # sshfs is network type
                "fuse": True,
                "options": {"defaults": True},
                "dump": {"enabled": False},
                "fsck": {"enabled": False},
            },
            {
                "target": "/decrypted",
                "source": "encfs#/encrypted",
                "driver": "fuse.encfs",
                "type": "overlay",  # encfs is overlay type
                "fuse": True,
                "options": {"defaults": True},
                "dump": {"enabled": False},
                "fsck": {"enabled": False},
            },
    ]

    assert result == expected
