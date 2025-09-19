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
from ansible_collections.o0_o.posix.plugins.module_utils.df_utils import parse_df_entry


@pytest.fixture
def filter_module() -> FilterModule:
    """Create a FilterModule instance for testing."""
    return FilterModule()


def test_df_filter_with_string_input(filter_module: FilterModule) -> None:
    """Test df filter with string input."""
    # Mock jc.parse to return predictable data
    mock_jc_data = [
        {
            "filesystem": "/dev/sda1",
            "1024_blocks": 20971520,
            "used": 5242880,
            "available": 15728640,
            "use_percent": 25,
            "mounted_on": "/"
        },
        {
            "filesystem": "/dev/sda2",
            "1024_blocks": 104857600,
            "used": 52428800,
            "available": 52428800,
            "use_percent": 50,
            "mounted_on": "/home"
        }
    ]

    df_output = """Filesystem     1024-blocks     Used Available Use% Mounted on
/dev/sda1        20971520  5242880  15728640  25% /
/dev/sda2       104857600 52428800  52428800  50% /home"""

    df_filter = filter_module.filters()["df"]
    with patch('ansible_collections.o0_o.posix.plugins.module_utils.jc_utils.jc.parse', return_value=mock_jc_data):
        result = df_filter(df_output)

    assert isinstance(result, list)
    assert len(result) == 2

    # Check first entry
    assert result[0]["mount"] == "/"
    assert result[0]["source"] == "/dev/sda1"
    assert "capacity" in result[0]
    assert "total" in result[0]["capacity"]
    assert "used" in result[0]["capacity"]

    # Check capacity structure
    capacity = result[0]["capacity"]
    assert "bytes" in capacity["total"]
    assert "pretty" in capacity["total"]
    assert capacity["total"]["bytes"] == 20971520 * 1024  # 20GB in bytes
    assert capacity["total"]["pretty"] == "20 GiB"

    assert "bytes" in capacity["used"]
    assert "pretty" in capacity["used"]
    assert "percent" in capacity["used"]
    assert capacity["used"]["bytes"] == 5242880 * 1024  # 5GB in bytes
    assert capacity["used"]["pretty"] == "5 GiB"

    # Verify percent calculation (not using df's percent)
    total_bytes = capacity["total"]["bytes"]
    used_bytes = capacity["used"]["bytes"]
    expected_percent = round((used_bytes / total_bytes) * 100, 2)
    assert capacity["used"]["percent"] == expected_percent
    assert capacity["used"]["percent"] == 25.0

    # Check second entry
    assert result[1]["mount"] == "/home"
    assert result[1]["source"] == "/dev/sda2"
    assert result[1]["capacity"]["used"]["percent"] == 50.0


def test_df_filter_with_dict_input(filter_module: FilterModule) -> None:
    """Test df filter with dict input (from command module)."""
    mock_jc_data = [
        {
            "filesystem": "/dev/sda1",
            "1024_blocks": 20971520,
            "used": 5242880,
            "mounted_on": "/"
        }
    ]

    command_result = {
        "stdout": """Filesystem     1024-blocks     Used Available Use% Mounted on
/dev/sda1        20971520  5242880  15728640  25% /""",
        "stderr": "",
        "rc": 0
    }

    df_filter = filter_module.filters()["df"]
    with patch('ansible_collections.o0_o.posix.plugins.module_utils.jc_utils.jc.parse', return_value=mock_jc_data):
        result = df_filter(command_result)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["mount"] == "/"
    assert result[0]["source"] == "/dev/sda1"


def test_df_filter_with_content_key(filter_module: FilterModule) -> None:
    """Test df filter with content key in dict."""
    mock_jc_data = [
        {
            "filesystem": "tmpfs",
            "1024_blocks": 1048576,
            "used": 0,
            "mounted_on": "/tmp"
        }
    ]

    slurp_result = {
        "content": "Filesystem     1024-blocks  Used Available Use% Mounted on\ntmpfs           1048576     0   1048576   0% /tmp"
    }

    df_filter = filter_module.filters()["df"]
    with patch('ansible_collections.o0_o.posix.plugins.module_utils.jc_utils.jc.parse', return_value=mock_jc_data):
        result = df_filter(slurp_result)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["mount"] == "/tmp"


def test_df_filter_without_jc(filter_module: FilterModule) -> None:
    """Test df filter raises error without jc."""
    df_filter = filter_module.filters()["df"]
    with patch('ansible_collections.o0_o.posix.plugins.module_utils.jc_utils.HAS_JC', False):
        with pytest.raises(AnsibleFilterError, match="jc library"):
            df_filter("some output")


def test_df_filter_with_invalid_dict(filter_module: FilterModule) -> None:
    """Test df filter with invalid dict input."""
    df_filter = filter_module.filters()["df"]
    invalid_dict = {"foo": "bar"}

    with pytest.raises(AnsibleFilterError):
        df_filter(invalid_dict)


def test_df_filter_zero_total_bytes(filter_module: FilterModule) -> None:
    """Test df filter handles zero total bytes gracefully."""
    mock_jc_data = [
        {
            "filesystem": "devtmpfs",
            "1024_blocks": 0,
            "used": 0,
            "mounted_on": "/dev"
        }
    ]

    df_filter = filter_module.filters()["df"]
    with patch('ansible_collections.o0_o.posix.plugins.module_utils.jc_utils.jc.parse', return_value=mock_jc_data):
        result = df_filter("dummy")

    assert len(result) == 1
    assert result[0]["mount"] == "/dev"
    if "capacity" in result[0] and "used" in result[0]["capacity"]:
        assert result[0]["capacity"]["used"]["percent"] == 0.0


def test_df_filter_missing_filesystem(filter_module: FilterModule) -> None:
    """Test df filter handles missing filesystem field."""
    mock_jc_data = [
        {
            "1024_blocks": 100000,
            "used": 50000,
            "mounted_on": "/mnt/test"
        }
    ]

    df_filter = filter_module.filters()["df"]
    with patch('ansible_collections.o0_o.posix.plugins.module_utils.jc_utils.jc.parse', return_value=mock_jc_data):
        result = df_filter("dummy")

    assert len(result) == 1
    assert result[0]["mount"] == "/mnt/test"
    assert "source" not in result[0]  # No source field when filesystem is missing


def test_df_filter_skip_invalid_entries(filter_module: FilterModule) -> None:
    """Test df filter skips entries without mounted_on."""
    mock_jc_data = [
        {
            "filesystem": "/dev/sda1",
            "1024_blocks": 100000,
            "mounted_on": "/"
        },
        {
            "filesystem": "/dev/sda2",
            "1024_blocks": 200000,
            # Missing mounted_on - should be skipped
        }
    ]

    df_filter = filter_module.filters()["df"]
    with patch('ansible_collections.o0_o.posix.plugins.module_utils.jc_utils.jc.parse', return_value=mock_jc_data):
        result = df_filter("dummy")

    assert len(result) == 1
    assert result[0]["mount"] == "/"


def test_df_filter_with_512_blocks(filter_module: FilterModule) -> None:
    """Test df filter with 512-byte blocks."""
    mock_jc_data = [
        {
            "filesystem": "/dev/vda1",
            "512_blocks": 41943040,  # 20GB in 512-byte blocks
            "used": 10485760,  # 5GB in 512-byte blocks
            "mounted_on": "/data"
        }
    ]

    df_filter = filter_module.filters()["df"]
    with patch('ansible_collections.o0_o.posix.plugins.module_utils.jc_utils.jc.parse', return_value=mock_jc_data):
        result = df_filter("dummy")

    assert len(result) == 1
    assert result[0]["mount"] == "/data"
    capacity = result[0]["capacity"]
    assert capacity["total"]["bytes"] == 41943040 * 512
    assert capacity["used"]["bytes"] == 10485760 * 512
    assert capacity["used"]["percent"] == 25.0


def test_df_filter_with_size_field(filter_module: FilterModule) -> None:
    """Test df filter with size field (df -h output)."""
    mock_jc_data = [
        {
            "filesystem": "/dev/sdb1",
            "size": "100G",
            "used": "25G",
            "available": "75G",
            "mounted_on": "/storage"
        }
    ]

    df_filter = filter_module.filters()["df"]
    with patch('ansible_collections.o0_o.posix.plugins.module_utils.jc_utils.jc.parse', return_value=mock_jc_data):
        result = df_filter("dummy")

    assert len(result) == 1
    assert result[0]["mount"] == "/storage"
    capacity = result[0]["capacity"]

    # parse_si should convert "100G" and "25G" properly
    assert capacity["total"]["bytes"] == 100 * 1024**3  # 100GB in bytes
    assert capacity["used"]["bytes"] == 25 * 1024**3   # 25GB in bytes
    assert capacity["used"]["percent"] == 25.0


def test_df_filter_without_parse_si(filter_module: FilterModule) -> None:
    """Test df filter works without parse_si (no capacity field)."""
    mock_jc_data = [
        {
            "filesystem": "/dev/sda1",
            "1024_blocks": 100000,
            "mounted_on": "/"
        }
    ]

    df_filter = filter_module.filters()["df"]
    with patch('ansible_collections.o0_o.posix.plugins.module_utils.df_utils.HAS_PARSE_SI', False):
        with patch('ansible_collections.o0_o.posix.plugins.module_utils.jc_utils.jc.parse', return_value=mock_jc_data):
            result = df_filter("dummy")

    assert len(result) == 1
    assert result[0]["mount"] == "/"
    assert result[0]["source"] == "/dev/sda1"
    assert "capacity" not in result[0]  # No capacity without parse_si


def test_df_filter_percent_calculation(filter_module: FilterModule) -> None:
    """Test that percent is calculated correctly and not taken from df."""
    mock_jc_data = [
        {
            "filesystem": "/dev/sda1",
            "1024_blocks": 1000000,
            "used": 333333,  # Exactly 33.3333%
            "use_percent": 34,  # df rounds to 34%
            "mounted_on": "/test"
        }
    ]

    df_filter = filter_module.filters()["df"]
    with patch('ansible_collections.o0_o.posix.plugins.module_utils.jc_utils.jc.parse', return_value=mock_jc_data):
        result = df_filter("dummy")

    assert len(result) == 1
    capacity = result[0]["capacity"]

    # Our calculation should be (333333 / 1000000) * 100 = 33.33
    assert capacity["used"]["percent"] == 33.33
    # Not 34 from df's use_percent field


def test_df_filter_parse_error(filter_module: FilterModule) -> None:
    """Test df filter handles jc parse errors."""
    df_filter = filter_module.filters()["df"]
    with patch('ansible_collections.o0_o.posix.plugins.module_utils.jc_utils.jc.parse', side_effect=Exception("Parse error")):
        with pytest.raises(AnsibleFilterError, match="df failed"):
            df_filter("invalid df output")
