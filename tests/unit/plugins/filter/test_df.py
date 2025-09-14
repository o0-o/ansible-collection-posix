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
from ansible_collections.o0_o.posix.tests.utils import find_mount_by_target


# Helper to format sizes like the si filter does
def format_size(size_bytes: int) -> str:
    """Format bytes as binary size using si filter."""
    si = SiFilter()
    result = si.si(f"{size_bytes}B", binary=True)
    return result.get("pretty", f"{size_bytes} B")


def parse_size(size_str: str) -> int:
    """Parse size string to bytes using si filter."""
    si = SiFilter()
    # Add B suffix if string ends with size prefix (K, M, G)
    if size_str and size_str[-1] in "KMGTPEZY":
        size_str = size_str + "B"
    result = si.si(size_str, binary=True)
    return result.get("bytes", 0)


@pytest.fixture
def filter_module() -> FilterModule:
    """Create a FilterModule instance for testing."""
    return FilterModule()


@pytest.mark.parametrize(
    "parsed_data,expected_targets,expected_sources",
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
            ["/", "/home", "/dev/shm"],
            ["/dev/sda1", "/dev/sda2", None],
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
            ["/"],
            ["/dev/vda1"],
        ),
        # Empty list
        ([], [], []),
    ],
)
def test_normalize_and_format_as_facts(
    filter_module: FilterModule,
    parsed_data: list,
    expected_targets: list,
    expected_sources: list,
) -> None:
    """Test _normalize_df_data and format_storage_as_facts with various df outputs."""
    # First normalize the data
    normalized = filter_module._normalize_df_data(parsed_data)
    # Then format as facts
    result = filter_module.format_storage_as_facts(normalized)
    
    assert isinstance(result, list)
    assert len(result) == len(expected_targets)
    
    # Check each mount has the expected target and source
    for i, target in enumerate(expected_targets):
        mount = find_mount_by_target(result, target)
        assert mount is not None, f"Mount with target {target} not found"
        assert mount["target"] == target
        if expected_sources[i] is not None:
            assert mount["source"] == expected_sources[i]
        else:
            # For tmpfs, source should be None
            assert mount.get("source") is None
        
        # Check capacity exists for all mounts
        assert "capacity" in mount
        assert "total" in mount["capacity"]
        assert "used" in mount["capacity"]
        assert "bytes" in mount["capacity"]["total"]
        assert "pretty" in mount["capacity"]["total"]


def test_format_without_si_filter(
    filter_module: FilterModule,
) -> None:
    """Test format_storage_as_facts raises error without si filter."""
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

    with patch(
        "ansible_collections.o0_o.posix.plugins.module_utils.storage_base.HAS_SI_FILTER", False
    ):
        normalized = filter_module._normalize_df_data(parsed_data)
        with pytest.raises(AnsibleFilterError, match="o0_o.utils.si"):
            filter_module.format_storage_as_facts(normalized)


def test_normalize_missing_mounted_on(
    filter_module: FilterModule,
) -> None:
    """Test _normalize_df_data skips entries without mounted_on."""
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
            # No mounted_on field - this should be skipped
        },
    ]

    normalized = filter_module._normalize_df_data(parsed_data)
    # Should only have 1 entry (the first one)
    assert len(normalized) == 1
    assert normalized[0]["target"] == "/"


def test_normalize_preserves_original(
    filter_module: FilterModule,
) -> None:
    """Test _normalize_df_data doesn't modify original data."""
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

    # Call method
    filter_module._normalize_df_data(original)

    # Ensure original wasn't modified
    assert original == original_copy


def test_virtual_filesystem_handling(
    filter_module: FilterModule,
) -> None:
    """Test that virtual filesystems like tmpfs are handled correctly."""
    parsed_data = [
        {
            "filesystem": "tmpfs",
            "1024_blocks": 2097152,
            "used": 0,
            "available": 2097152,
            "mounted_on": "/dev/shm",
        }
    ]
    
    normalized = filter_module._normalize_df_data(parsed_data)
    result = filter_module.format_storage_as_facts(normalized)
    
    mount = result[0]
    assert mount["target"] == "/dev/shm"
    assert mount["type"] == "virtual"
    # df doesn't provide filesystem type (driver), only source
    assert mount.get("source") is None
    # No pseudo field anymore - pseudo filesystems have source="kernel"


def test_network_filesystem_handling(
    filter_module: FilterModule,
) -> None:
    """Test that network filesystems are handled correctly."""
    parsed_data = [
        {
            "filesystem": "nfs-server:/export",
            "1024_blocks": 1048576,
            "used": 524288,
            "available": 524288,
            "mounted_on": "/mnt/nfs",
        }
    ]
    
    normalized = filter_module._normalize_df_data(parsed_data)
    result = filter_module.format_storage_as_facts(normalized)
    
    mount = result[0]
    assert mount["target"] == "/mnt/nfs"
    assert mount["source"] == "nfs-server:/export"
    assert mount["type"] == "network"


def test_shm_filesystem_handling(
    filter_module: FilterModule,
) -> None:
    """Test that shm is correctly identified as tmpfs."""
    parsed_data = [
        {
            "filesystem": "shm",
            "1024_blocks": 65536,
            "used": 136,
            "available": 65400,
            "mounted_on": "/dev/shm",
        }
    ]
    
    normalized = filter_module._normalize_df_data(parsed_data)
    result = filter_module.format_storage_as_facts(normalized)
    
    mount = result[0]
    assert mount["target"] == "/dev/shm"
    # shm becomes tmpfs driver, source stays as shm
    assert mount["driver"] == "tmpfs"
    assert mount["source"] == "shm"
    assert mount["type"] == "virtual"
