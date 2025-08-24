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

import pytest

from ansible_collections.o0_o.posix.plugins.filter.df import FilterModule


@pytest.fixture
def filter_module() -> FilterModule:
    """Create a FilterModule instance for testing."""
    return FilterModule()


@pytest.mark.parametrize(
    "parsed_data,expected",
    [
        # Standard df output with multiple filesystems
        (
            [
                {
                    "filesystem": "/dev/sda1",
                    "size": 20971520,
                    "used": 5242880,
                    "available": 15728640,
                    "use_percent": 25,
                    "mounted_on": "/",
                },
                {
                    "filesystem": "/dev/sda2",
                    "size": 104857600,
                    "used": 52428800,
                    "available": 52428800,
                    "use_percent": 50,
                    "mounted_on": "/home",
                },
                {
                    "filesystem": "tmpfs",
                    "size": 2097152,
                    "used": 0,
                    "available": 2097152,
                    "use_percent": 0,
                    "mounted_on": "/dev/shm",
                },
            ],
            {
                "filesystems": {
                    "/": {
                        "filesystem": "/dev/sda1",
                        "size": 20971520,
                        "used": 5242880,
                        "available": 15728640,
                        "use_percent": 25,
                    },
                    "/home": {
                        "filesystem": "/dev/sda2",
                        "size": 104857600,
                        "used": 52428800,
                        "available": 52428800,
                        "use_percent": 50,
                    },
                    "/dev/shm": {
                        "filesystem": "tmpfs",
                        "size": 2097152,
                        "used": 0,
                        "available": 2097152,
                        "use_percent": 0,
                    },
                }
            },
        ),
        # Single filesystem
        (
            [
                {
                    "filesystem": "/dev/vda1",
                    "size": 10485760,
                    "used": 2097152,
                    "available": 8388608,
                    "use_percent": 20,
                    "mounted_on": "/",
                }
            ],
            {
                "filesystems": {
                    "/": {
                        "filesystem": "/dev/vda1",
                        "size": 10485760,
                        "used": 2097152,
                        "available": 8388608,
                        "use_percent": 20,
                    }
                }
            },
        ),
        # Entry without mounted_on field (should be skipped)
        (
            [
                {
                    "filesystem": "/dev/sda1",
                    "size": 20971520,
                    "used": 5242880,
                    "available": 15728640,
                    "use_percent": 25,
                    "mounted_on": "/",
                },
                {
                    "filesystem": "/dev/sda2",
                    "size": 104857600,
                    "used": 52428800,
                    "available": 52428800,
                    "use_percent": 50,
                    # No mounted_on field
                },
            ],
            {
                "filesystems": {
                    "/": {
                        "filesystem": "/dev/sda1",
                        "size": 20971520,
                        "used": 5242880,
                        "available": 15728640,
                        "use_percent": 25,
                    }
                }
            },
        ),
        # Empty list
        ([], {"filesystems": {}}),
        # Network filesystems
        (
            [
                {
                    "filesystem": "nfs-server:/export",
                    "size": 1073741824,
                    "used": 536870912,
                    "available": 536870912,
                    "use_percent": 50,
                    "mounted_on": "/mnt/nfs",
                },
                {
                    "filesystem": "//smb-server/share",
                    "size": 2147483648,
                    "used": 1073741824,
                    "available": 1073741824,
                    "use_percent": 50,
                    "mounted_on": "/mnt/smb",
                },
            ],
            {
                "filesystems": {
                    "/mnt/nfs": {
                        "filesystem": "nfs-server:/export",
                        "size": 1073741824,
                        "used": 536870912,
                        "available": 536870912,
                        "use_percent": 50,
                    },
                    "/mnt/smb": {
                        "filesystem": "//smb-server/share",
                        "size": 2147483648,
                        "used": 1073741824,
                        "available": 1073741824,
                        "use_percent": 50,
                    },
                }
            },
        ),
        # Special mount points with spaces (edge case)
        (
            [
                {
                    "filesystem": "/dev/sda1",
                    "size": 10485760,
                    "used": 2097152,
                    "available": 8388608,
                    "use_percent": 20,
                    "mounted_on": "/mnt/my mount",
                }
            ],
            {
                "filesystems": {
                    "/mnt/my mount": {
                        "filesystem": "/dev/sda1",
                        "size": 10485760,
                        "used": 2097152,
                        "available": 8388608,
                        "use_percent": 20,
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
    result = filter_module._format_as_facts(parsed_data)
    assert result == expected


def test_format_as_facts_preserves_original(filter_module: FilterModule) -> None:
    """Test that _format_as_facts doesn't modify the original parsed data."""
    original = [
        {
            "filesystem": "/dev/sda1",
            "size": 20971520,
            "used": 5242880,
            "available": 15728640,
            "use_percent": 25,
            "mounted_on": "/",
        }
    ]
    # Make a deep copy to compare later
    import copy

    original_copy = copy.deepcopy(original)

    # Call the method
    filter_module._format_as_facts(original)

    # Ensure original wasn't modified
    assert original == original_copy
