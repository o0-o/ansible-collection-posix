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

from typing import Any, Dict
from unittest.mock import patch

import pytest
from ansible.errors import AnsibleFilterError

from ansible_collections.o0_o.posix.plugins.filter.uname import FilterModule


@pytest.fixture
def filter_module() -> FilterModule:
    """Create a FilterModule instance for testing."""
    return FilterModule()


def test_uname_basic(filter_module: FilterModule) -> None:
    """Test uname filter with basic output."""
    # Test with actual uname -a output
    uname_output = (
        "Linux testhost 5.15.0-91-generic #101-Ubuntu SMP "
        "Tue Nov 14 13:30:08 UTC 2023 x86_64 x86_64 x86_64 GNU/Linux"
    )

    uname_filter = filter_module.filters()["uname"]
    result = uname_filter(uname_output)

    # Verify the normalized structure
    assert "kernel" in result
    assert result["kernel"]["name"] == "linux"
    assert result["kernel"]["pretty"] == "Linux"
    assert result["kernel"]["version"]["id"] == "5.15.0-91-generic"
    assert result["architecture"] == "x86_64"
    assert "hostname" in result
    assert result["hostname"]["short"] == "testhost"


def test_uname_with_fqdn(filter_module: FilterModule) -> None:
    """Test uname filter with FQDN hostname."""
    # Test with actual uname -a output with FQDN
    uname_output = (
        "Linux webserver.example.com 5.15.0-91-generic #101-Ubuntu SMP "
        "Tue Nov 14 13:30:08 UTC 2023 x86_64 x86_64 x86_64 GNU/Linux"
    )

    uname_filter = filter_module.filters()["uname"]
    result = uname_filter(uname_output)

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


def test_uname_without_utils(filter_module: FilterModule) -> None:
    """Test that uname raises error without o0_o.utils."""
    uname_output = "Linux testhost 5.15.0-91-generic #101 x86_64 GNU/Linux"

    # Test with HAS_PARSE_HOSTNAME = False
    uname_filter = filter_module.filters()["uname"]
    with patch(
        "ansible_collections.o0_o.posix.plugins.module_utils."
        "uname_utils.HAS_PARSE_HOSTNAME",
        False,
    ):
        with pytest.raises(AnsibleFilterError, match="o0_o.utils collection"):
            uname_filter(uname_output)


class TestUnameUtils:
    """Test the uname utilities from module_utils."""

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
    def test_parse_uname_entry(
        self,
        parsed_data: Dict[str, Any],
        expected: Dict[str, Any],
    ) -> None:
        """Test parse_uname_entry with various input scenarios."""
        from ansible_collections.o0_o.posix.plugins.module_utils.uname_utils import parse_uname_entry

        # Mock parse_hostname to return what we expect
        if "hostname" in expected:
            mock_return = dict(expected["hostname"])
        else:
            mock_return = {"short": "localhost"}

        with patch(
            "ansible_collections.o0_o.posix.plugins.module_utils."
            "uname_utils.parse_hostname",
            return_value=mock_return,
        ):
            result = parse_uname_entry(parsed_data)
            assert result == expected

    def test_architecture_fallback_processor(self) -> None:
        """Test architecture falls back to processor field."""
        parsed = {"processor": "amd64"}

        from ansible_collections.o0_o.posix.plugins.module_utils.uname_utils import parse_uname_entry
        result = parse_uname_entry(parsed)

        assert result["architecture"] == "amd64"

    def test_architecture_fallback_hardware_platform(self) -> None:
        """Test architecture falls back to hardware_platform field."""
        parsed = {"hardware_platform": "x86_64"}

        from ansible_collections.o0_o.posix.plugins.module_utils.uname_utils import parse_uname_entry
        result = parse_uname_entry(parsed)

        assert result["architecture"] == "x86_64"

    def test_architecture_skips_unknown(self) -> None:
        """Test architecture skips 'unknown' values."""
        parsed = {"processor": "unknown", "hardware_platform": "x86_64"}

        from ansible_collections.o0_o.posix.plugins.module_utils.uname_utils import parse_uname_entry
        result = parse_uname_entry(parsed)

        assert result["architecture"] == "x86_64"
