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

import sys
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
from ansible.errors import AnsibleFilterError


# Create a mock HostnameFilter class
class MockHostnameFilter:
    """Mock HostnameFilter for testing."""

    def hostname(self, value: str) -> Dict[str, str]:
        """Mock hostname parsing."""
        hostname_map = {
            "webserver.example.com": {
                "short": "webserver",
                "long": "webserver.example.com",
            },
            "macbook.local": {"short": "macbook", "long": "macbook.local"},
            "localhost": {"short": "localhost"},
        }
        return hostname_map.get(value, {"short": value.split(".")[0]})


# Mock the o0_o.utils module before importing uname
mock_filter_module = MagicMock()
mock_filter_module.HostnameFilter = MockHostnameFilter
sys.modules["ansible_collections.o0_o.utils.plugins.filter"] = (
    mock_filter_module
)

from ansible_collections.o0_o.posix.plugins.filter.uname import FilterModule


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


def test_uname_default_mode(
    filter_module: FilterModule, mock_parse_command: MagicMock
) -> None:
    """Test uname filter in default mode (facts=False)."""
    # Setup mock to return parsed data
    parsed_data = {
        "kernel_name": "Linux",
        "node_name": "testhost",
        "kernel_release": "5.15.0-91-generic",
        "machine": "x86_64",
    }
    mock_parse_command.return_value = parsed_data

    # Test with string input
    result = filter_module.uname("Linux testhost 5.15.0-91-generic x86_64")

    # Verify parse_command was called
    mock_parse_command.assert_called_once_with(
        "Linux testhost 5.15.0-91-generic x86_64", "uname"
    )

    # Verify raw parsed data is returned
    assert result == parsed_data


def test_uname_facts_mode(
    filter_module: FilterModule, mock_parse_command: MagicMock
) -> None:
    """Test uname filter in facts mode."""
    # Setup mock to return parsed data
    parsed_data = {
        "kernel_name": "Linux",
        "node_name": "webserver.example.com",
        "kernel_release": "5.15.0-91-generic",
        "machine": "x86_64",
    }
    mock_parse_command.return_value = parsed_data

    # Test with facts=True
    # Patch HostnameFilter in the uname module
    with patch(
        "ansible_collections.o0_o.posix.plugins.filter.uname.HostnameFilter",
        MockHostnameFilter,
        create=True,
    ):
        with patch(
            "ansible_collections.o0_o.posix.plugins.filter."
            "uname.HAS_HOSTNAME_FILTER",
            True,
        ):
            result = filter_module.uname("dummy", facts=True)

    # Verify the structure
    assert "kernel" in result
    assert result["kernel"]["name"] == "linux"
    assert result["kernel"]["pretty"] == "Linux"
    assert result["kernel"]["version"]["id"] == "5.15.0-91-generic"

    assert "architecture" in result
    assert result["architecture"] == "x86_64"

    assert "hostname" in result
    assert result["hostname"]["short"] == "webserver"
    assert result["hostname"]["long"] == "webserver.example.com"


def test_uname_facts_mode_without_utils(
    filter_module: FilterModule, mock_parse_command: MagicMock
) -> None:
    """Test that facts mode raises error without o0_o.utils."""
    mock_parse_command.return_value = {"kernel_name": "Linux"}

    # Test with HAS_HOSTNAME_FILTER = False
    with patch(
        "ansible_collections.o0_o.posix.plugins.filter."
        "uname.HAS_HOSTNAME_FILTER",
        False,
    ):
        with pytest.raises(AnsibleFilterError, match="o0_o.utils collection"):
            filter_module.uname("dummy", facts=True)


class TestFormatAsFacts:
    """Test the _format_as_facts method directly."""

    @pytest.mark.parametrize(
        "parsed_data,expected",
        [
            # Complete Linux data with FQDN
            (
                {
                    "kernel_name": "Linux",
                    "node_name": "webserver.example.com",
                    "kernel_release": "5.15.0-91-generic",
                    "machine": "x86_64",
                },
                {
                    "kernel": {
                        "pretty": "Linux",
                        "name": "linux",
                        "version": {"id": "5.15.0-91-generic"},
                    },
                    "architecture": "x86_64",
                    "hostname": {
                        "short": "webserver",
                        "long": "webserver.example.com",
                    },
                },
            ),
            # Darwin/macOS system
            (
                {
                    "kernel_name": "Darwin",
                    "node_name": "macbook.local",
                    "kernel_release": "23.6.0",
                    "machine": "arm64",
                },
                {
                    "kernel": {
                        "pretty": "Darwin",
                        "name": "darwin",
                        "version": {"id": "23.6.0"},
                    },
                    "architecture": "arm64",
                    "hostname": {
                        "short": "macbook",
                        "long": "macbook.local",
                    },
                },
            ),
            # Short hostname only (no FQDN)
            (
                {
                    "kernel_name": "Linux",
                    "node_name": "localhost",
                    "machine": "x86_64",
                },
                {
                    "kernel": {"pretty": "Linux", "name": "linux"},
                    "architecture": "x86_64",
                    "hostname": {"short": "localhost"},
                },
            ),
            # Kernel name with spaces
            (
                {"kernel_name": "GNU kFreeBSD", "machine": "amd64"},
                {
                    "kernel": {
                        "pretty": "GNU kFreeBSD",
                        "name": "gnu_kfreebsd",
                    },
                    "architecture": "amd64",
                },
            ),
            # Minimal data
            ({}, {}),
        ],
    )
    def test_format_as_facts(
        self,
        filter_module: FilterModule,
        parsed_data: Dict[str, Any],
        expected: Dict[str, Any],
    ) -> None:
        """Test _format_as_facts with various input scenarios."""
        # Patch HostnameFilter in the uname module
        with patch(
            "ansible_collections.o0_o.posix.plugins.filter."
            "uname.HostnameFilter",
            MockHostnameFilter,
            create=True,
        ):
            result = filter_module._format_as_facts(parsed_data)
            assert result == expected

    def test_architecture_fallback_processor(
        self, filter_module: FilterModule
    ) -> None:
        """Test architecture falls back to processor field."""
        parsed = {"processor": "amd64"}

        result = filter_module._format_as_facts(parsed)

        assert result["architecture"] == "amd64"

    def test_architecture_fallback_hardware_platform(
        self, filter_module: FilterModule
    ) -> None:
        """Test architecture falls back to hardware_platform field."""
        parsed = {"hardware_platform": "x86_64"}

        result = filter_module._format_as_facts(parsed)

        assert result["architecture"] == "x86_64"

    def test_architecture_skips_unknown(
        self, filter_module: FilterModule
    ) -> None:
        """Test architecture skips 'unknown' values."""
        parsed = {"processor": "unknown", "hardware_platform": "x86_64"}

        result = filter_module._format_as_facts(parsed)

        assert result["architecture"] == "x86_64"
