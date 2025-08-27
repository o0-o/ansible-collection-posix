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

from unittest.mock import patch

import pytest
from ansible.errors import AnsibleFilterError

from ansible_collections.o0_o.posix.plugins.filter.df import FilterModule
from ansible_collections.o0_o.utils.plugins.filter import SiFilter


# Helper to format sizes like the si filter does
def format_size(size_bytes: int) -> str:
    """Format bytes as binary size using si filter."""
    si = SiFilter()
    result = si.si(f"{size_bytes}B", binary=True)
    return result.get("pretty", f"{size_bytes} B")


def parse_size(size_str: str) -> int:
    """Parse size string to bytes using si filter."""
    si = SiFilter()
    # Add B suffix if the string ends with just a size prefix (K, M, G, etc.)
    if size_str and size_str[-1] in "KMGTPEZY":
        size_str = size_str + "B"
    result = si.si(size_str, binary=True)
    return result.get("bytes", 0)


@pytest.fixture
def filter_module() -> FilterModule:
    """Create a FilterModule instance for testing."""
    return FilterModule()


@pytest.mark.parametrize(
    "parsed_data,expected",
    [
        # Standard df output with 1024_blocks
        (
            [
                {
                    "filesystem": "/dev/sda1",
                    "1024_blocks": 20971520,
                    "used": 5242880,
                    "available": 15728640,
                    "use_percent": 25,
                    "mounted_on": "/",
                },
                {
                    "filesystem": "/dev/sda2",
                    "1024_blocks": 104857600,
                    "used": 52428800,
                    "available": 52428800,
                    "use_percent": 50,
                    "mounted_on": "/home",
                },
                {
                    "filesystem": "tmpfs",
                    "1024_blocks": 2097152,
                    "used": 0,
                    "available": 2097152,
                    "use_percent": 0,
                    "mounted_on": "/dev/shm",
                },
            ],
            {
                "mounts": {
                    "/": {
                        "device": "/dev/sda1",
                        "capacity": {
                            "total": {
                                "bytes": 20971520 * 1024,
                                "pretty": format_size(20971520 * 1024),
                            },
                            "used": {
                                "bytes": 5242880 * 1024,
                                "pretty": format_size(5242880 * 1024),
                            },
                        },
                    },
                    "/home": {
                        "device": "/dev/sda2",
                        "capacity": {
                            "total": {
                                "bytes": 104857600 * 1024,
                                "pretty": format_size(104857600 * 1024),
                            },
                            "used": {
                                "bytes": 52428800 * 1024,
                                "pretty": format_size(52428800 * 1024),
                            },
                        },
                    },
                    "/dev/shm": {
                        "device": "tmpfs",
                        "capacity": {
                            "total": {
                                "bytes": 2097152 * 1024,
                                "pretty": format_size(2097152 * 1024),
                            },
                            "used": {
                                "bytes": 0,
                                "pretty": format_size(0),
                            },
                        },
                    },
                }
            },
        ),
        # Single filesystem with 512_blocks
        (
            [
                {
                    "filesystem": "/dev/vda1",
                    "512_blocks": 20971520,
                    "used": 4194304,
                    "available": 16777216,
                    "use_percent": 20,
                    "mounted_on": "/",
                }
            ],
            {
                "mounts": {
                    "/": {
                        "device": "/dev/vda1",
                        "capacity": {
                            "total": {
                                "bytes": 20971520 * 512,
                                "pretty": format_size(20971520 * 512),
                            },
                            "used": {
                                "bytes": 4194304 * 512,
                                "pretty": format_size(4194304 * 512),
                            },
                        },
                    }
                }
            },
        ),
        # Empty list
        ([], {"mounts": {}}),
        # Network filesystems
        (
            [
                {
                    "filesystem": "nfs-server:/export",
                    "1024_blocks": 1048576,
                    "used": 524288,
                    "available": 524288,
                    "use_percent": 50,
                    "mounted_on": "/mnt/nfs",
                },
                {
                    "filesystem": "//smb-server/share",
                    "1024_blocks": 2097152,
                    "used": 1048576,
                    "available": 1048576,
                    "use_percent": 50,
                    "mounted_on": "/mnt/smb",
                },
            ],
            {
                "mounts": {
                    "/mnt/nfs": {
                        "device": "nfs-server:/export",
                        "capacity": {
                            "total": {
                                "bytes": 1048576 * 1024,
                                "pretty": format_size(1048576 * 1024),
                            },
                            "used": {
                                "bytes": 524288 * 1024,
                                "pretty": format_size(524288 * 1024),
                            },
                        },
                    },
                    "/mnt/smb": {
                        "device": "//smb-server/share",
                        "capacity": {
                            "total": {
                                "bytes": 2097152 * 1024,
                                "pretty": format_size(2097152 * 1024),
                            },
                            "used": {
                                "bytes": 1048576 * 1024,
                                "pretty": format_size(1048576 * 1024),
                            },
                        },
                    },
                }
            },
        ),
        # Special mount points with spaces (edge case)
        (
            [
                {
                    "filesystem": "/dev/sda1",
                    "1024_blocks": 10240,
                    "used": 2048,
                    "available": 8192,
                    "use_percent": 20,
                    "mounted_on": "/mnt/my mount",
                }
            ],
            {
                "mounts": {
                    "/mnt/my mount": {
                        "device": "/dev/sda1",
                        "capacity": {
                            "total": {
                                "bytes": 10240 * 1024,
                                "pretty": format_size(10240 * 1024),
                            },
                            "used": {
                                "bytes": 2048 * 1024,
                                "pretty": format_size(2048 * 1024),
                            },
                        },
                    }
                }
            },
        ),
        # Test with df -h style output (size as string)
        (
            [
                {
                    "filesystem": "/dev/sda1",
                    "size": "20G",
                    "used": "5G",
                    "available": "15G",
                    "use_percent": 25,
                    "mounted_on": "/",
                }
            ],
            {
                "mounts": {
                    "/": {
                        "device": "/dev/sda1",
                        "capacity": {
                            "total": {
                                "bytes": parse_size("20G"),
                                "pretty": format_size(parse_size("20G")),
                            },
                            "used": {
                                "bytes": parse_size("5G"),
                                "pretty": format_size(parse_size("5G")),
                            },
                        },
                    }
                }
            },
        ),
    ],
)
def test_format_as_facts(
    filter_module: FilterModule,
    parsed_data: list,
    expected: dict,
) -> None:
    """Test _format_as_facts method with various df outputs."""
    # No need to patch since we're using real o0_o.utils.si filter
    result = filter_module._format_as_facts(parsed_data)
    assert result == expected


def test_format_as_facts_without_si_filter(filter_module: FilterModule) -> None:
    """Test that _format_as_facts raises error without o0_o.utils.si filter."""
    parsed_data = [
        {
            "filesystem": "/dev/sda1",
            "1024_blocks": 20971520,
            "used": 5242880,
            "available": 15728640,
            "use_percent": 25,
            "mounted_on": "/",
        }
    ]

    with patch("ansible_collections.o0_o.posix.plugins.filter.df.HAS_SI_FILTER", False):
        with pytest.raises(AnsibleFilterError, match="o0_o.utils collection"):
            filter_module._format_as_facts(parsed_data)


def test_format_as_facts_missing_mounted_on(filter_module: FilterModule) -> None:
    """Test that _format_as_facts raises error when mounted_on field is missing."""
    parsed_data = [
        {
            "filesystem": "/dev/sda1",
            "1024_blocks": 20971520,
            "used": 5242880,
            "available": 15728640,
            "use_percent": 25,
            "mounted_on": "/",
        },
        {
            "filesystem": "/dev/sda2",
            "1024_blocks": 104857600,
            "used": 52428800,
            "available": 52428800,
            "use_percent": 50,
            # No mounted_on field - this should cause an error
        },
    ]

    with pytest.raises(AnsibleFilterError, match="df output missing 'mounted_on' field"):
        filter_module._format_as_facts(parsed_data)


def test_format_as_facts_preserves_original(filter_module: FilterModule) -> None:
    """Test that _format_as_facts doesn't modify the original parsed data."""
    original = [
        {
            "filesystem": "/dev/sda1",
            "1024_blocks": 20971520,
            "used": 5242880,
            "available": 15728640,
            "use_percent": 25,
            "mounted_on": "/",
        }
    ]
    # Make a deep copy to compare later
    import copy

    original_copy = copy.deepcopy(original)

    # Call the method - no need to patch since we're using real o0_o.utils.si filter
    filter_module._format_as_facts(original)

    # Ensure original wasn't modified
    assert original == original_copy
