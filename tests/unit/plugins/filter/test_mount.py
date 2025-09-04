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
    assert root_mount["source"] == "/dev/sda1"
    assert root_mount["type"] == "device"
    assert root_mount["filesystem"] == "ext4"
    assert root_mount["fuse"] is False
    assert root_mount["options"] == {
        "rw": True,
        "relatime": True,
        "errors": "remount-ro",
    }

    # Verify home mount
    home_mount = result["mounts"]["/home"]
    assert home_mount["source"] == "/dev/sda2"
    assert home_mount["type"] == "device"
    assert home_mount["filesystem"] == "ext4"
    assert home_mount["fuse"] is False
    assert home_mount["options"] == {"rw": True, "relatime": True}

    # Verify tmpfs mount (virtual filesystem)
    shm_mount = result["mounts"]["/dev/shm"]
    assert (
        shm_mount.get("source") is None
    )  # Virtual filesystems have source=None
    assert shm_mount["type"] == "virtual"
    assert shm_mount["filesystem"] == "tmpfs"
    assert shm_mount["pseudo"] is False  # tmpfs is virtual but not pseudo
    assert shm_mount["fuse"] is False
    assert shm_mount["options"] == {"rw": True, "nosuid": True, "nodev": True}


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
                            "source": "/dev/sda1",
                            "type": "device",
                            "filesystem": "ext4",
                            "fuse": False,
                            "options": {"rw": True, "relatime": True},
                        },
                        "/boot": {
                            "source": "/dev/sda2",
                            "type": "device",
                            "filesystem": "ext4",
                            "fuse": False,
                            "options": {"rw": True, "relatime": True},
                        },
                    }
                },
            ),
            # Network filesystem (NFS)
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
                            "type": "network",
                            "filesystem": "nfs",
                            "fuse": False,
                            "options": {
                                "rw": True,
                                "vers": "4.2",
                                "rsize": "1048576",
                            },
                        }
                    }
                },
            ),
            # Network filesystem (CIFS/SMB)
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
                            "type": "network",
                            "filesystem": "cifs",
                            "fuse": False,
                            "options": {
                                "rw": True,
                                "uid": "1000",
                                "gid": "1000",
                            },
                        }
                    }
                },
            ),
            # macOS mounts with type field
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
                            "source": "/dev/disk3s1s1",
                            "type": "device",
                            "filesystem": "apfs",
                            "fuse": False,
                            "options": {
                                "local": True,
                                "journaled": True,
                                "nobrowse": True,
                            },
                        },
                        "/dev": {
                            "source": None,
                            "type": "virtual",
                            "filesystem": "devfs",
                            "pseudo": True,  # devfs is a pseudo filesystem
                            "fuse": False,
                            "options": {"local": True, "nobrowse": True},
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
                            "source": "/dev/disk3s1s1",
                            "type": "device",
                            "filesystem": "apfs",
                            "fuse": False,
                            "options": {
                                "sealed": True,
                                "local": True,
                                "journaled": True,
                            },
                        },
                        "/dev": {
                            "source": None,
                            "type": "virtual",
                            "filesystem": "devfs",
                            "pseudo": True,
                            "fuse": False,
                            "options": {"local": True, "nobrowse": True},
                        },
                    }
                },
            ),
            # Virtual and pseudo filesystems
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
                            "source": None,
                            "type": "virtual",
                            "filesystem": "proc",
                            "pseudo": True,  # proc is a pseudo filesystem
                            "fuse": False,
                            "options": {
                                "rw": True,
                                "nosuid": True,
                                "nodev": True,
                                "noexec": True,
                            },
                        },
                        "/sys": {
                            "source": None,
                            "type": "virtual",
                            "filesystem": "sysfs",
                            "pseudo": True,  # sysfs is a pseudo filesystem
                            "fuse": False,
                            "options": {
                                "rw": True,
                                "nosuid": True,
                                "nodev": True,
                                "noexec": True,
                            },
                        },
                        "/run": {
                            "source": None,
                            "type": "virtual",
                            "filesystem": "tmpfs",
                            "pseudo": False,  # tmpfs is virtual but not pseudo
                            "fuse": False,
                            "options": {
                                "rw": True,
                                "nosuid": True,
                                "nodev": True,
                            },
                        },
                    }
                },
            ),
            # Empty options list
            (
                [
                    {
                        "filesystem": "/dev/sda1",
                        "mount_point": "/",
                        "type": "ext4",
                        "options": [],
                    }
                ],
                {
                    "mounts": {
                        "/": {
                            "source": "/dev/sda1",
                            "type": "device",
                            "filesystem": "ext4",
                            "fuse": False,
                        }
                    }
                },
            ),
            # Mount with no mount_point (should skip)
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
            # Overlay filesystem
            (
                [
                    {
                        "filesystem": "overlay",
                        "mount_point": "/var/lib/docker/overlay2",
                        "type": "overlay",
                        "options": [
                            "rw",
                            "lowerdir=/lower",
                            "upperdir=/upper",
                        ],
                    }
                ],
                {
                    "mounts": {
                        "/var/lib/docker/overlay2": {
                            "type": "overlay",
                            "filesystem": "overlay",
                            "fuse": False,
                            "options": {
                                "rw": True,
                                "lowerdir": "/lower",
                                "upperdir": "/upper",
                            },
                        }
                    }
                },
            ),
            # FUSE filesystem with subtype
            (
                [
                    {
                        "filesystem": "portal",
                        "mount_point": "/mnt/portal",
                        "type": "fuse",
                        "options": ["rw", "nosuid", "nodev", "subtype=sshfs"],
                    }
                ],
                {
                    "mounts": {
                        "/mnt/portal": {
                            "source": "portal",
                            "type": "network",  # sshfs is a network filesystem
                            # subtype replaces generic fuse
                            "filesystem": "sshfs",
                            "fuse": True,
                            "options": {
                                "rw": True,
                                "nosuid": True,
                                "nodev": True,
                            },
                        }
                    }
                },
            ),
            # FUSE filesystem without subtype (ambiguous)
            (
                [
                    {
                        "filesystem": "some.fuse.mount",
                        "mount_point": "/mnt/fuse",
                        "type": "fuse",
                        "options": ["rw", "nosuid", "nodev"],
                    }
                ],
                {
                    "mounts": {
                        "/mnt/fuse": {
                            "source": "some.fuse.mount",
                            # No filesystem when FUSE type ambiguous
                            "fuse": True,
                            "options": {
                                "rw": True,
                                "nosuid": True,
                                "nodev": True,
                            },
                        }
                    }
                },
            ),
            # FUSE filesystem with fuse. prefix
            (
                [
                    {
                        "filesystem": "sshfs#user@host:",
                        "mount_point": "/mnt/ssh",
                        "type": "fuse.sshfs",
                        "options": ["rw", "nosuid", "nodev"],
                    }
                ],
                {
                    "mounts": {
                        "/mnt/ssh": {
                            "source": "sshfs#user@host:",
                            # fuse.sshfs detected as sshfs network FS
                            "type": "network",
                            "filesystem": "fuse.sshfs",
                            "fuse": True,
                            "options": {
                                "rw": True,
                                "nosuid": True,
                                "nodev": True,
                            },
                        }
                    }
                },
            ),
            # Docker overlay filesystem (no explicit source)
            (
                [
                    {
                        "filesystem": "overlay",
                        "mount_point": "/",
                        "type": "overlay",
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
                {
                    "mounts": {
                        "/": {
                            # No source field for overlay
                            "type": "overlay",
                            "filesystem": "overlay",
                            "fuse": False,
                            "options": {
                                "rw": True,
                                "relatime": True,
                                "lowerdir": (
                                    "/var/lib/docker/overlay2/l/ABC:"
                                    "/var/lib/docker/overlay2/l/DEF"
                                ),
                                "upperdir": (
                                    "/var/lib/docker/overlay2/xyz/diff"
                                ),
                                "workdir": "/var/lib/docker/overlay2/xyz/work",
                                "nouserxattr": True,
                            },
                        }
                    }
                },
            ),
            # Bind mount
            (
                [
                    {
                        "filesystem": "/dev/sda1",
                        "mount_point": "/mnt/bind",
                        "type": "ext4",
                        "options": ["rw", "relatime", "bind"],
                    }
                ],
                {
                    "mounts": {
                        "/mnt/bind": {
                            "source": "/dev/sda1",
                            # bind mounts are classified as overlay
                            "type": "overlay",
                            "filesystem": "ext4",
                            "fuse": False,
                            "options": {
                                "rw": True,
                                "relatime": True,
                                "bind": True,
                            },
                        }
                    }
                },
            ),
            # Recursive bind mount
            (
                [
                    {
                        "filesystem": "/dev/sda1",
                        "mount_point": "/mnt/rbind",
                        "type": "ext4",
                        "options": ["rw", "relatime", "rbind"],
                    }
                ],
                {
                    "mounts": {
                        "/mnt/rbind": {
                            "source": "/dev/sda1",
                            # rbind mounts are classified as overlay
                            "type": "overlay",
                            "filesystem": "ext4",
                            "fuse": False,
                            "options": {
                                "rw": True,
                                "relatime": True,
                                "rbind": True,
                            },
                        }
                    }
                },
            ),
            # Source as 'none'
            (
                [
                    {
                        "filesystem": "none",
                        "mount_point": "/proc",
                        "type": "proc",
                        "options": ["rw"],
                    }
                ],
                {
                    "mounts": {
                        "/proc": {
                            "source": None,  # 'none' becomes None
                            "type": "virtual",
                            "filesystem": "proc",
                            "pseudo": True,
                            "fuse": False,
                            "options": {"rw": True},
                        }
                    }
                },
            ),
            # Source as '-'
            (
                [
                    {
                        "filesystem": "-",
                        "mount_point": "/sys",
                        "type": "sysfs",
                        "options": ["rw"],
                    }
                ],
                {
                    "mounts": {
                        "/sys": {
                            "source": None,  # '-' becomes None
                            "type": "virtual",
                            "filesystem": "sysfs",
                            "pseudo": True,
                            "fuse": False,
                            "options": {"rw": True},
                        }
                    }
                },
            ),
            # fuseblk (NTFS)
            (
                [
                    {
                        "filesystem": "/dev/sda1",
                        "mount_point": "/mnt/ntfs",
                        "type": "fuseblk",
                        "options": ["rw", "relatime", "allow_other"],
                    }
                ],
                {
                    "mounts": {
                        "/mnt/ntfs": {
                            "source": "/dev/sda1",
                            "type": "device",  # fuseblk is device type
                            # No filesystem when fuseblk without subtype
                            "fuse": True,
                            "options": {
                                "rw": True,
                                "relatime": True,
                                "allow_other": True,
                            },
                        }
                    }
                },
            ),
        ],
    )
    def test_format_as_facts(
        self,
        filter_module: FilterModule,
        parsed_data: List[Dict[str, Any]],
        expected: Dict[str, Any],
    ) -> None:
        """Test _format_as_facts with various mount configurations."""
        result = filter_module._format_as_facts(parsed_data)
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
