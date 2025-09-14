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
from ansible_collections.o0_o.posix.tests.utils import find_mount_by_target


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
    assert isinstance(result, list)
    assert len(result) == 3

    # Verify root mount
    root_mount = find_mount_by_target(result, "/")
    assert root_mount is not None
    assert root_mount["source"] == "/dev/sda1"
    assert root_mount["type"] == "regular"
    assert root_mount["driver"] == "ext4"
    assert root_mount["fuse"] is False
    assert root_mount["options"] == {
        "rw": True,
        "relatime": True,
        "errors": "remount-ro",
    }

    # Verify home mount
    home_mount = find_mount_by_target(result, "/home")
    assert home_mount is not None
    assert home_mount["source"] == "/dev/sda2"
    assert home_mount["type"] == "regular"
    assert home_mount["driver"] == "ext4"
    assert home_mount["fuse"] is False
    assert home_mount["options"] == {"rw": True, "relatime": True}

    # Verify tmpfs mount (virtual filesystem)
    shm_mount = find_mount_by_target(result, "/dev/shm")
    assert shm_mount is not None
    assert (
        shm_mount.get("source") is None
    )  # Virtual filesystems have source=None
    assert shm_mount["type"] == "virtual"
    assert shm_mount["driver"] == "tmpfs"
    assert shm_mount["fuse"] is False
    assert shm_mount["options"] == {"rw": True, "nosuid": True, "nodev": True}


class TestNormalizeMountData:
    """Test the _normalize_mount_data method."""

    def test_normalize_linux_style(self, filter_module: FilterModule) -> None:
        """Test normalization of Linux-style mount data with type field."""
        parsed = [
            {
                "filesystem": "/dev/sda1",
                "mount_point": "/",
                "type": "ext4",
                "options": ["rw", "relatime"],
            },
        ]

        normalized = filter_module._normalize_mount_data(parsed)

        assert len(normalized) == 1
        assert normalized[0]["target"] == "/"
        assert normalized[0]["source"] == "/dev/sda1"
        assert normalized[0]["driver"] == "ext4"
        assert normalized[0]["options"] == ["rw", "relatime"]

    def test_normalize_macos_style(self, filter_module: FilterModule) -> None:
        """Test normalization of macOS-style mount data (type in options)."""
        parsed = [
            {
                "filesystem": "/dev/disk3s1s1",
                "mount_point": "/",
                "options": ["apfs", "local", "journaled"],
            },
        ]

        normalized = filter_module._normalize_mount_data(parsed)

        assert len(normalized) == 1
        assert normalized[0]["target"] == "/"
        assert normalized[0]["source"] == "/dev/disk3s1s1"
        assert normalized[0]["driver"] == "apfs"
        assert normalized[0]["options"] == [
            "local",
            "journaled",
        ]  # type removed


class TestFormatStorageAsFacts:
    """Test the format_storage_as_facts method (inherited from StorageBase)."""

    @pytest.mark.parametrize(
        "normalized_data,expected",
        [
            # Standard Linux mounts with /dev/ devices (normalized format)
            (
                [
                    {
                        "source": "/dev/sda1",
                        "target": "/",
                        "driver": "ext4",
                        "options": ["rw", "relatime"],
                    },
                    {
                        "source": "/dev/sda2",
                        "target": "/boot",
                        "driver": "ext4",
                        "options": ["rw", "relatime"],
                    },
                ],
                [
                    {
                        "target": "/",
                        "source": "/dev/sda1",
                        "type": "regular",
                        "driver": "ext4",
                        "fuse": False,
                        "options": {"rw": True, "relatime": True},
                    },
                    {
                        "target": "/boot",
                        "source": "/dev/sda2",
                        "type": "regular",
                        "driver": "ext4",
                        "fuse": False,
                        "options": {"rw": True, "relatime": True},
                    },
                ],
            ),
            # Network filesystem (NFS) (normalized format)
            (
                [
                    {
                        "source": "nfs-server:/export/home",
                        "target": "/mnt/nfs",
                        "driver": "nfs",
                        "options": ["rw", "vers=4.2", "rsize=1048576"],
                    }
                ],
                [
                    {
                        "target": "/mnt/nfs",
                        "source": "nfs-server:/export/home",
                        "type": "network",
                        "driver": "nfs",
                        "fuse": False,
                        "options": {
                            "rw": True,
                            "vers": "4.2",
                            "rsize": "1048576",
                        },
                    }
                ],
            ),
            # Network filesystem (CIFS/SMB) (normalized format)
            (
                [
                    {
                        "source": "//smb-server/share",
                        "target": "/mnt/smb",
                        "driver": "cifs",
                        "options": ["rw", "uid=1000", "gid=1000"],
                    }
                ],
                [
                    {
                        "target": "/mnt/smb",
                        "source": "//smb-server/share",
                        "type": "network",
                        "driver": "cifs",
                        "fuse": False,
                        "options": {
                            "rw": True,
                            "uid": "1000",
                            "gid": "1000",
                        },
                    }
                ],
            ),
            # macOS mounts (normalized format - type already extracted)
            (
                [
                    {
                        "source": "/dev/disk3s1s1",
                        "target": "/",
                        "driver": "apfs",
                        "options": ["local", "journaled", "nobrowse"],
                    },
                    {
                        "source": "devfs",
                        "target": "/dev",
                        "driver": "devfs",
                        "options": ["local", "nobrowse"],
                    },
                ],
                [
                    {
                        "target": "/",
                        "source": "/dev/disk3s1s1",
                        "type": "regular",
                        "driver": "apfs",
                        "fuse": False,
                        "options": {
                            "local": True,
                            "journaled": True,
                            "nobrowse": True,
                        },
                    },
                    {
                        "target": "/dev",
                        "source": "kernel",
                        "type": "virtual",
                        "driver": "devfs",
                        "fuse": False,
                        "options": {"local": True, "nobrowse": True},
                    },
                ],
            ),
            # Virtual filesystems (normalized format)
            (
                [
                    {
                        "source": "tmpfs",
                        "target": "/dev/shm",
                        "driver": "tmpfs",
                        "options": ["rw", "nosuid", "nodev"],
                    },
                    {
                        "source": "devfs",
                        "target": "/dev",
                        "driver": "devfs",
                        "options": ["local", "nobrowse"],
                    },
                ],
                [
                    {
                        "target": "/dev/shm",
                        "source": None,  # tmpfs doesn't need source
                        "type": "virtual",
                        "driver": "tmpfs",
                        "fuse": False,
                        "options": {
                            "rw": True,
                            "nosuid": True,
                            "nodev": True,
                        },
                    },
                    {
                        "target": "/dev",
                        "source": "kernel",
                        "type": "virtual",
                        "driver": "devfs",
                        "fuse": False,
                        "options": {"local": True, "nobrowse": True},
                    },
                ],
            ),
            # Virtual and pseudo filesystems (normalized format)
            (
                [
                    {
                        "source": "proc",
                        "target": "/proc",
                        "driver": "proc",
                        "options": ["rw", "nosuid", "nodev", "noexec"],
                    },
                    {
                        "source": "sysfs",
                        "target": "/sys",
                        "driver": "sysfs",
                        "options": ["rw", "nosuid", "nodev", "noexec"],
                    },
                    {
                        "source": "tmpfs",
                        "target": "/run",
                        "driver": "tmpfs",
                        "options": ["rw", "nosuid", "nodev"],
                    },
                ],
                [
                    {
                        "target": "/proc",
                        "source": "kernel",
                        "type": "virtual",
                        "driver": "proc",
                        "fuse": False,
                        "options": {
                            "rw": True,
                            "nosuid": True,
                            "nodev": True,
                            "noexec": True,
                        },
                    },
                    {
                        "target": "/sys",
                        "source": "kernel",
                        "type": "virtual",
                        "driver": "sysfs",
                        "fuse": False,
                        "options": {
                            "rw": True,
                            "nosuid": True,
                            "nodev": True,
                            "noexec": True,
                        },
                    },
                    {
                        "target": "/run",
                        "source": None,
                        "type": "virtual",
                        "driver": "tmpfs",
                        "fuse": False,
                        "options": {
                            "rw": True,
                            "nosuid": True,
                            "nodev": True,
                        },
                    },
                ],
            ),
            # Empty options list (normalized format)
            (
                [
                    {
                        "source": "/dev/sda1",
                        "target": "/",
                        "driver": "ext4",
                        "options": [],
                    }
                ],
                [
                    {
                        "target": "/",
                        "source": "/dev/sda1",
                        "type": "regular",
                        "driver": "ext4",
                        "fuse": False,
                        "options": {},  # Empty options list becomes empty dict
                    }
                ],
            ),
            # Mount with no mount_point (still included, just no target field)
            (
                [
                    {
                        "source": "/dev/sda1",
                        "driver": "ext4",
                        "options": ["rw"],
                    }
                ],
                [
                    {
                        # No target field
                        "source": "/dev/sda1",
                        "type": "regular",
                        "driver": "ext4",
                        "fuse": False,
                        "options": {"rw": True},
                    }
                ],
            ),
            # Overlay filesystem
            (
                [
                    {
                        "source": "overlay",
                        "target": "/var/lib/docker/overlay2",
                        "driver": "overlay",
                        "options": [
                            "rw",
                            "lowerdir=/lower",
                            "upperdir=/upper",
                        ],
                    }
                ],
                [
                    {
                        "target": "/var/lib/docker/overlay2",
                        "type": "overlay",
                        "driver": "overlay",
                        "fuse": False,
                        "options": {
                            "rw": True,
                            "lowerdir": "/lower",
                            "upperdir": "/upper",
                        },
                    }
                ],
            ),
            # FUSE filesystem with subtype (normalized format)
            (
                [
                    {
                        "source": "portal",
                        "target": "/mnt/portal",
                        "driver": "fuse",
                        "options": ["rw", "nosuid", "nodev", "subtype=sshfs"],
                    }
                ],
                [
                    {
                        "target": "/mnt/portal",
                        "source": "portal",
                        "type": "network",  # sshfs is a network filesystem
                        # subtype replaces generic fuse
                        "driver": "sshfs",
                        "fuse": True,
                        "options": {
                            "rw": True,
                            "nosuid": True,
                            "nodev": True,
                        },
                    }
                ],
            ),
            # FUSE filesystem without subtype (ambiguous)
            (
                [
                    {
                        "source": "some.fuse.mount",
                        "target": "/mnt/fuse",
                        "driver": "fuse",
                        "options": ["rw", "nosuid", "nodev"],
                    }
                ],
                [
                    {
                        "target": "/mnt/fuse",
                        "source": "some.fuse.mount",
                        # No filesystem when FUSE type ambiguous
                        "fuse": True,
                        "options": {
                            "rw": True,
                            "nosuid": True,
                            "nodev": True,
                        },
                    }
                ],
            ),
            # FUSE filesystem with fuse. prefix (normalized format)
            (
                [
                    {
                        "source": "sshfs#user@host:",
                        "target": "/mnt/ssh",
                        "driver": "fuse.sshfs",
                        "options": ["rw", "nosuid", "nodev"],
                    }
                ],
                [
                    {
                        "target": "/mnt/ssh",
                        "source": "sshfs#user@host:",
                        # fuse.sshfs detected as sshfs network FS
                        "type": "network",
                        "driver": "fuse.sshfs",
                        "fuse": True,
                        "options": {
                            "rw": True,
                            "nosuid": True,
                            "nodev": True,
                        },
                    }
                ],
            ),
            # Docker overlay filesystem (no explicit source)
            (
                [
                    {
                        "source": "overlay",
                        "target": "/",
                        "driver": "overlay",
                        "options": [
                            "rw",
                            "relatime",
                            (
                                "lowerdir=/var/lib/docker/overlay2/l/ABC:"
                                "/var/lib/docker/overlay2/l/DEF"
                            ),
                            "upperdir=/var/lib/docker/overlay2/xyz/diff",
                            "workdir=/var/lib/docker/overlay2/xyz/work",
                            "nouserxattr",
                        ],
                    }
                ],
                [
                    {
                        "target": "/",
                        # No source field for overlay
                        "type": "overlay",
                        "driver": "overlay",
                        "fuse": False,
                        "options": {
                            "rw": True,
                            "relatime": True,
                            "lowerdir": (
                                "/var/lib/docker/overlay2/l/ABC:"
                                "/var/lib/docker/overlay2/l/DEF"
                            ),
                            "upperdir": ("/var/lib/docker/overlay2/xyz/diff"),
                            "workdir": "/var/lib/docker/overlay2/xyz/work",
                            "nouserxattr": True,
                        },
                    }
                ],
            ),
            # Bind mount (normalized format)
            (
                [
                    {
                        "source": "/dev/sda1",
                        "target": "/mnt/bind",
                        "driver": "ext4",
                        "options": ["rw", "relatime", "bind"],
                    }
                ],
                [
                    {
                        "target": "/mnt/bind",
                        "source": "/dev/sda1",
                        # bind mounts are classified as overlay
                        "type": "overlay",
                        "driver": "ext4",
                        "fuse": False,
                        "options": {
                            "rw": True,
                            "relatime": True,
                            "bind": True,
                        },
                    }
                ],
            ),
            # Recursive bind mount (normalized format)
            (
                [
                    {
                        "source": "/dev/sda1",
                        "target": "/mnt/rbind",
                        "driver": "ext4",
                        "options": ["rw", "relatime", "rbind"],
                    }
                ],
                [
                    {
                        "target": "/mnt/rbind",
                        "source": "/dev/sda1",
                        # rbind mounts are classified as overlay
                        "type": "overlay",
                        "driver": "ext4",
                        "fuse": False,
                        "options": {
                            "rw": True,
                            "relatime": True,
                            "rbind": True,
                        },
                    }
                ],
            ),
            # Source as 'none' (normalized format)
            (
                [
                    {
                        "source": "none",
                        "target": "/proc",
                        "driver": "proc",
                        "options": ["rw"],
                    }
                ],
                [
                    {
                        "target": "/proc",
                        "source": "kernel",  # 'none' becomes "kernel" for pseudo filesystems
                        "type": "virtual",
                        "driver": "proc",
                        "fuse": False,
                        "options": {"rw": True},
                    }
                ],
            ),
            # Source as '-' (normalized format)
            (
                [
                    {
                        "source": "-",
                        "target": "/sys",
                        "driver": "sysfs",
                        "options": ["rw"],
                    }
                ],
                [
                    {
                        "target": "/sys",
                        "source": "kernel",  # sysfs is pseudo, so gets source="kernel"
                        "type": "virtual",
                        "driver": "sysfs",
                        "fuse": False,
                        "options": {"rw": True},
                    }
                ],
            ),
            # fuseblk (NTFS) (normalized format)
            (
                [
                    {
                        "source": "/dev/sda1",
                        "target": "/mnt/ntfs",
                        "driver": "fuseblk",
                        "options": ["rw", "relatime", "allow_other"],
                    }
                ],
                [
                    {
                        "target": "/mnt/ntfs",
                        "source": "/dev/sda1",
                        "type": "regular",  # fuseblk is device type
                        # No filesystem when fuseblk without subtype
                        "fuse": True,
                        "options": {
                            "rw": True,
                            "relatime": True,
                            "allow_other": True,
                        },
                    }
                ],
            ),
        ],
    )
    def test_format_storage_as_facts(
        self,
        filter_module: FilterModule,
        normalized_data: List[Dict[str, Any]],
        expected: List[Dict[str, Any]],
    ) -> None:
        """Test format_storage_as_facts with various storage configurations."""
        result = filter_module.format_storage_as_facts(normalized_data)
        assert result == expected


def test_mount_with_dict_input(
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

    # Test with dict input
    command_result = {
        "stdout": "/dev/sda1 on / type ext4 (rw)",
        "stdout_lines": ["/dev/sda1 on / type ext4 (rw)"],
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
