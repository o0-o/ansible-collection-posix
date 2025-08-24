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
from unittest.mock import MagicMock

import pytest


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


class TestFormatAsFacts:
    """Test suite for _format_as_facts method."""

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
        result = filter_module._format_as_facts(parsed_data)
        assert result == expected

    @pytest.mark.parametrize(
        "parsed_data,expected_arch",
        [
            # Architecture from machine field
            ({"kernel_name": "Linux", "machine": "x86_64"}, "x86_64"),
            # Architecture from processor field
            ({"kernel_name": "Linux", "processor": "aarch64"}, "aarch64"),
            # Architecture from hardware_platform field
            (
                {
                    "kernel_name": "Linux",
                    "processor": "unknown",
                    "hardware_platform": "ppc64le",
                },
                "ppc64le",
            ),
            # No architecture with unknown values
            (
                {
                    "kernel_name": "Linux",
                    "processor": "unknown",
                    "hardware_platform": "unknown",
                },
                None,
            ),
            # Machine field takes precedence
            (
                {
                    "kernel_name": "Linux",
                    "machine": "x86_64",
                    "processor": "aarch64",
                    "hardware_platform": "ppc64le",
                },
                "x86_64",
            ),
        ],
    )
    def test_architecture_detection(
        self,
        filter_module: FilterModule,
        parsed_data: Dict[str, Any],
        expected_arch: str | None,
    ) -> None:
        """Test architecture detection with fallback scenarios."""
        result = filter_module._format_as_facts(parsed_data)
        if expected_arch:
            assert result["architecture"] == expected_arch
        else:
            assert "architecture" not in result
