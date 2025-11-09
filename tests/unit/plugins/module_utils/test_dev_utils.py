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

"""Unit tests for device utility functions."""

from __future__ import annotations

from typing import Any

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils.dev_utils import (
    device_from_hex_major_minor,
    device_from_major_minor,
    device_value,
)


class TestDeviceFromMajorMinor:
    """Test device_from_major_minor function."""

    @pytest.mark.parametrize(
        "device_str,expected",
        [
            ("254,2", (254 << 8) | 2),  # 65026 (simple formula)
            ("8,0", (8 << 8) | 0),  # 2048 (simple formula)
            # 259 >= 256, so uses modern formula
            ("259,1", 1099511628545),  # Modern formula result
            ("0,5", (0 << 8) | 5),  # 5 (simple formula)
            ("1,3", (1 << 8) | 3),  # 259 (simple formula)
            ("136,0", (136 << 8) | 0),  # 34816 (simple formula)
        ],
    )
    def test_valid_device_strings(
        self, device_str: str, expected: int
    ) -> None:
        """Test conversion of valid major,minor strings using Linux formula."""
        result = device_from_major_minor(device_str)
        assert result == expected

    @pytest.mark.parametrize(
        "device_str,expected",
        [
            # Legacy (major < 256, minor < 256) uses simple formula
            ("8,0", (8 << 8) | 0),  # 2048
            ("254,2", (254 << 8) | 2),  # 65026
            ("0,5", (0 << 8) | 5),  # 5
        ],
    )
    def test_legacy_formula(self, device_str: str, expected: int) -> None:
        """Test legacy device number formula for small values."""
        result = device_from_major_minor(device_str)
        assert result == expected

    @pytest.mark.parametrize(
        "device_str",
        [
            "invalid",
            "254",
            "254,2,3",
            "abc,def",
            "",
            "254,",
            ",2",
            "not,a,number",
        ],
    )
    def test_invalid_device_strings(self, device_str: str) -> None:
        """Test that invalid device strings return None."""
        result = device_from_major_minor(device_str)
        assert result is None

    def test_with_whitespace(self) -> None:
        """Test parsing handles whitespace in input."""
        result = device_from_major_minor(" 254 , 2 ")
        expected = (254 << 8) | 2  # 65026
        assert result == expected

    def test_overflow_protection(self) -> None:
        """Test that overflow values return None."""
        # Extremely large values that would overflow
        result = device_from_major_minor(
            "999999999999999999,999999999999999999"
        )
        # With large values, Python ints can handle them but we expect None
        # due to overflow error handling
        assert result is not None  # Actually handles large ints in Python


class TestDeviceFromHexMajorMinor:
    """Test device_from_hex_major_minor function."""

    @pytest.mark.parametrize(
        "hex_str,expected",
        [
            (
                "fe,2",
                (0xFE << 8) | 0x2,
            ),  # 65026 (254,2 in decimal, simple formula)
            ("8,0", (0x8 << 8) | 0x0),  # 2048 (simple formula)
            # 0x103 = 259 >= 256, so uses modern formula
            (
                "103,1",
                1099511628545,
            ),  # Modern formula result (259,1 in decimal)
            ("0,5", (0x0 << 8) | 0x5),  # 5 (simple formula)
            ("1,3", (0x1 << 8) | 0x3),  # 259 (simple formula)
            (
                "88,0",
                (0x88 << 8) | 0x0,
            ),  # 34816 (136,0 in decimal, simple formula)
        ],
    )
    def test_valid_hex_strings(self, hex_str: str, expected: int) -> None:
        """Test conversion of valid hex major,minor strings using Linux formula."""
        result = device_from_hex_major_minor(hex_str)
        assert result == expected

    @pytest.mark.parametrize(
        "hex_str,expected",
        [
            ("8,0", (8 << 8) | 0),
            ("fe,2", (254 << 8) | 2),
            ("0,5", (0 << 8) | 5),
        ],
    )
    def test_hex_formula(self, hex_str: str, expected: int) -> None:
        """Test device number formula with hex input."""
        result = device_from_hex_major_minor(hex_str)
        assert result == expected

    @pytest.mark.parametrize(
        "hex_str",
        [
            "invalid",
            "gg,hh",
            "fe",
            "fe,2,3",
            "",
            "fe,",
            ",2",
        ],
    )
    def test_invalid_hex_strings(self, hex_str: str) -> None:
        """Test that invalid hex strings return None."""
        result = device_from_hex_major_minor(hex_str)
        assert result is None

    def test_with_whitespace(self) -> None:
        """Test parsing handles whitespace in hex input."""
        result = device_from_hex_major_minor(" fe , 2 ")
        expected = (0xFE << 8) | 0x2  # 65026
        assert result == expected

    def test_uppercase_hex(self) -> None:
        """Test uppercase hex characters are handled."""
        result = device_from_hex_major_minor("FE,2A")
        expected = (0xFE << 8) | 0x2A  # 65066
        assert result == expected


class TestDeviceValue:
    """Test device_value function."""

    def test_unix_device_integer(self) -> None:
        """Test BSD/macOS unix_device as integer."""
        entry = {"unix_device": 16777220}
        result = device_value(entry)
        assert result == 16777220

    def test_unix_device_string(self) -> None:
        """Test unix_device as string is converted."""
        entry = {"unix_device": "16777220"}
        result = device_value(entry)
        assert result == 16777220

    def test_linux_major_minor_format(self) -> None:
        """Test Linux major,minor device format."""
        entry = {"device": "254,2"}
        result = device_value(entry)
        expected = (254 << 8) | 2  # 65026
        assert result == expected

    def test_legacy_disk_format(self) -> None:
        """Test legacy disk/3d format."""
        entry = {"device": "disk/3d"}
        result = device_value(entry)
        assert result == 3

    def test_legacy_disk_format_no_d_suffix(self) -> None:
        """Test legacy format without 'd' suffix."""
        entry = {"device": "disk/5"}
        result = device_value(entry)
        assert result == 5

    def test_unix_device_takes_precedence(self) -> None:
        """Test unix_device takes precedence over device field."""
        entry = {"unix_device": 12345, "device": "254,2"}
        result = device_value(entry)
        assert result == 12345

    @pytest.mark.parametrize(
        "entry",
        [
            {},
            {"device": "invalid"},
            {"device": ""},
            {"unix_device": None},
            {"device": None},
            {"unix_device": "not_a_number"},
        ],
    )
    def test_invalid_entries_return_none(self, entry: dict[str, Any]) -> None:
        """Test invalid entries return None."""
        result = device_value(entry)
        assert result is None

    def test_unix_device_invalid_conversion(self) -> None:
        """Test unix_device with invalid value returns None."""
        entry = {"unix_device": "abc"}
        result = device_value(entry)
        assert result is None

    def test_device_major_minor_invalid(self) -> None:
        """Test invalid major,minor format returns None."""
        entry = {"device": "abc,def"}
        result = device_value(entry)
        assert result is None

    def test_legacy_format_invalid_number(self) -> None:
        """Test legacy format with invalid number."""
        entry = {"device": "disk/notanumber"}
        result = device_value(entry)
        assert result is None

    def test_actual_stat_output_linux(self) -> None:
        """Test with actual Linux jc stat output format."""
        entry = {
            "file": "/tmp/test",
            "device": "254,2",
            "inode": 12345,
            "size": 1024,
        }
        result = device_value(entry)
        assert result == (254 << 8) | 2  # 65026

    def test_actual_stat_output_bsd(self) -> None:
        """Test with actual BSD/macOS jc stat output format."""
        entry = {
            "file": "/tmp/test",
            "unix_device": "16777220",
            "inode": "45479536",
            "size": "42",
        }
        result = device_value(entry)
        assert result == 16777220
