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

from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from ansible_collections.o0_o.posix.plugins.filter.mount import FilterModule


@pytest.fixture
def filter_module() -> FilterModule:
    """Create a FilterModule instance for testing."""
    return FilterModule()


@pytest.fixture
def mock_parse_command(monkeypatch) -> MagicMock:
    """Mock the parse_command method."""
    mock = MagicMock()
    monkeypatch.setattr(FilterModule, "parse_command", mock)
    return mock


def test_mount_default_mode(
    filter_module: FilterModule, mock_parse_command: MagicMock
) -> None:
    """Test mount filter in default mode (facts=False)."""
    # Setup mock to return parsed data
    parsed_data = [
        {
            "filesystem": "/dev/sda1",
            "mount_point": "/",
            "type": "ext4",
            "options": ["rw", "relatime", "errors=remount-ro"],
        },
        {
            "filesystem": "/dev/sda2",
            "mount_point": "/home",
            "type": "ext4",
            "options": ["rw", "relatime"],
        },
    ]
    mock_parse_command.return_value = parsed_data

    # Test with string input
    result = filter_module.mount(
        "/dev/sda1 on / type ext4 (rw,relatime,errors=remount-ro)"
    )

    # Verify parse_command was called
    mock_parse_command.assert_called_once_with(
        "/dev/sda1 on / type ext4 (rw,relatime,errors=remount-ro)", "mount"
    )

    # Verify raw parsed data is returned
    assert result == parsed_data


def test_mount_facts_mode(
    filter_module: FilterModule, mock_parse_command: MagicMock
) -> None:
    """Test mount filter in facts mode."""
    # Setup mock to return parsed data
    parsed_data = [
        {
            "filesystem": "/dev/sda1",
            "mount_point": "/",
            "type": "ext4",
            "options": ["rw", "relatime", "errors=remount-ro"],
        },
        {
            "filesystem": "/dev/sda2",
            "mount_point": "/home",
            "type": "ext4",
            "options": ["rw", "relatime"],
        },
        {
            "filesystem": "tmpfs",
            "mount_point": "/dev/shm",
            "type": "tmpfs",
            "options": ["rw", "nosuid", "nodev"],
        },
    ]
    mock_parse_command.return_value = parsed_data

    # Test with facts=True
    result = filter_module.mount("dummy", facts=True)

    # Verify the structure
    assert "mounts" in result
    assert "/" in result["mounts"]
    assert "/home" in result["mounts"]
    assert "/dev/shm" in result["mounts"]

    # Verify root mount
    root_mount = result["mounts"]["/"]
    assert root_mount["device"] == "/dev/sda1"
    assert root_mount["filesystem"] == "ext4"
    assert root_mount["options"] == ["rw", "relatime", "errors=remount-ro"]

    # Verify home mount
    home_mount = result["mounts"]["/home"]
    assert home_mount["device"] == "/dev/sda2"
    assert home_mount["filesystem"] == "ext4"
    assert home_mount["options"] == ["rw", "relatime"]

    # Verify tmpfs mount (no device since it's not /dev/)
    shm_mount = result["mounts"]["/dev/shm"]
    assert "device" not in shm_mount
    assert shm_mount["filesystem"] == "tmpfs"
    assert shm_mount["options"] == ["rw", "nosuid", "nodev"]


class TestFormatAsFacts:
    """Test the _format_as_facts method directly."""

    @pytest.mark.parametrize(
        "parsed_data,expected",
        [
            # Standard Linux mounts with /dev/ devices
            (
                [
                    {
                        "filesystem": "/dev/sda1",
                        "mount_point": "/",
                        "type": "ext4",
                        "options": ["rw", "relatime"],
                    },
                    {
                        "filesystem": "/dev/sda2",
                        "mount_point": "/boot",
                        "type": "ext4",
                        "options": ["rw", "relatime"],
                    },
                ],
                {
                    "mounts": {
                        "/": {
                            "device": "/dev/sda1",
                            "filesystem": "ext4",
                            "options": ["rw", "relatime"],
                        },
                        "/boot": {
                            "device": "/dev/sda2",
                            "filesystem": "ext4",
                            "options": ["rw", "relatime"],
                        },
                    }
                },
            ),
            # Network filesystem (NFS with source field)
            (
                [
                    {
                        "filesystem": "nfs-server:/export/home",
                        "mount_point": "/mnt/nfs",
                        "type": "nfs",
                        "options": ["rw", "vers=4.2", "rsize=1048576"],
                    }
                ],
                {
                    "mounts": {
                        "/mnt/nfs": {
                            "source": "nfs-server:/export/home",
                            "filesystem": "nfs",
                            "options": ["rw", "vers=4.2", "rsize=1048576"],
                        }
                    }
                },
            ),
            # Network filesystem (CIFS/SMB with source field)
            (
                [
                    {
                        "filesystem": "//smb-server/share",
                        "mount_point": "/mnt/smb",
                        "type": "cifs",
                        "options": ["rw", "uid=1000", "gid=1000"],
                    }
                ],
                {
                    "mounts": {
                        "/mnt/smb": {
                            "source": "//smb-server/share",
                            "filesystem": "cifs",
                            "options": ["rw", "uid=1000", "gid=1000"],
                        }
                    }
                },
            ),
            # macOS mounts with mixed device types (with type field)
            (
                [
                    {
                        "filesystem": "/dev/disk3s1s1",
                        "mount_point": "/",
                        "type": "apfs",
                        "options": ["local", "journaled", "nobrowse"],
                    },
                    {
                        "filesystem": "devfs",
                        "mount_point": "/dev",
                        "type": "devfs",
                        "options": ["local", "nobrowse"],
                    },
                ],
                {
                    "mounts": {
                        "/": {
                            "device": "/dev/disk3s1s1",
                            "filesystem": "apfs",
                            "options": ["local", "journaled", "nobrowse"],
                        },
                        "/dev": {
                            "filesystem": "devfs",
                            "options": ["local", "nobrowse"],
                        },
                    }
                },
            ),
            # macOS mounts without type field (fs type in first option)
            (
                [
                    {
                        "filesystem": "/dev/disk3s1s1",
                        "mount_point": "/",
                        "options": ["apfs", "sealed", "local", "journaled"],
                    },
                    {
                        "filesystem": "devfs",
                        "mount_point": "/dev",
                        "options": ["devfs", "local", "nobrowse"],
                    },
                ],
                {
                    "mounts": {
                        "/": {
                            "device": "/dev/disk3s1s1",
                            "filesystem": "apfs",
                            "options": ["sealed", "local", "journaled"],
                        },
                        "/dev": {
                            "filesystem": "devfs",
                            "options": ["local", "nobrowse"],
                        },
                    }
                },
            ),
            # Virtual filesystems (no devices)
            (
                [
                    {
                        "filesystem": "proc",
                        "mount_point": "/proc",
                        "type": "proc",
                        "options": ["rw", "nosuid", "nodev", "noexec"],
                    },
                    {
                        "filesystem": "sysfs",
                        "mount_point": "/sys",
                        "type": "sysfs",
                        "options": ["rw", "nosuid", "nodev", "noexec"],
                    },
                    {
                        "filesystem": "tmpfs",
                        "mount_point": "/run",
                        "type": "tmpfs",
                        "options": ["rw", "nosuid", "nodev"],
                    },
                ],
                {
                    "mounts": {
                        "/proc": {
                            "filesystem": "proc",
                            "options": ["rw", "nosuid", "nodev", "noexec"],
                        },
                        "/sys": {
                            "filesystem": "sysfs",
                            "options": ["rw", "nosuid", "nodev", "noexec"],
                        },
                        "/run": {
                            "filesystem": "tmpfs",
                            "options": ["rw", "nosuid", "nodev"],
                        },
                    }
                },
            ),
            # Missing mount_point (should be skipped)
            (
                [
                    {
                        "filesystem": "/dev/sda1",
                        "type": "ext4",
                        "options": ["rw"],
                    }
                ],
                {"mounts": {}},
            ),
            # Empty data
            ([], {"mounts": {}}),
            # Minimal mount info
            (
                [{"mount_point": "/tmp"}],
                {"mounts": {"/tmp": {}}},
            ),
            # Mount with only device and mount_point
            (
                [
                    {
                        "filesystem": "/dev/sdb1",
                        "mount_point": "/data",
                    }
                ],
                {"mounts": {"/data": {"device": "/dev/sdb1"}}},
            ),
            # Mount with non-device filesystem and mount_point
            (
                [
                    {
                        "filesystem": "tmpfs",
                        "mount_point": "/tmp",
                    }
                ],
                {"mounts": {"/tmp": {}}},
            ),
            # Mount with options (no type) - first option becomes type
            (
                [
                    {
                        "filesystem": "tmpfs",
                        "mount_point": "/run",
                        "options": ["tmpfs"],
                    }
                ],
                {"mounts": {"/run": {"filesystem": "tmpfs"}}},
            ),
        ],
    )
    def test_format_as_facts(
        self,
        filter_module: FilterModule,
        parsed_data: List[Dict[str, Any]],
        expected: Dict[str, Any],
    ) -> None:
        """Test _format_as_facts with various input scenarios."""
        result = filter_module._format_as_facts(parsed_data)
        assert result == expected


def test_mount_with_command_result_dict(
    filter_module: FilterModule, mock_parse_command: MagicMock
) -> None:
    """Test mount filter with command result dict input."""
    parsed_data = [
        {
            "filesystem": "/dev/sda1",
            "mount_point": "/",
            "type": "ext4",
            "options": ["rw"],
        }
    ]
    mock_parse_command.return_value = parsed_data

    # Test with dict input (like from command module)
    command_result = {
        "stdout": "/dev/sda1 on / type ext4 (rw)",
        "stderr": "",
        "rc": 0,
    }
    result = filter_module.mount(command_result)

    # Verify parse_command was called with the dict
    mock_parse_command.assert_called_once_with(command_result, "mount")
    assert result == parsed_data


def test_mount_with_list_input(
    filter_module: FilterModule, mock_parse_command: MagicMock
) -> None:
    """Test mount filter with list of lines input."""
    parsed_data = [
        {
            "filesystem": "/dev/sda1",
            "mount_point": "/",
            "type": "ext4",
            "options": ["rw"],
        }
    ]
    mock_parse_command.return_value = parsed_data

    # Test with list input
    lines = ["/dev/sda1 on / type ext4 (rw)"]
    result = filter_module.mount(lines)

    # Verify parse_command was called with the list
    mock_parse_command.assert_called_once_with(lines, "mount")
    assert result == parsed_data
