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

"""Unit tests for JC filter plugin."""

from __future__ import annotations

import pytest

from ansible.errors import AnsibleFilterError
from ansible_collections.o0_o.posix.plugins.filter.jc import FilterModule
from ansible_collections.o0_o.posix.plugins.filter_utils import JCBase


class TestJCBase:
    """Test JCBase utility class methods."""

    @pytest.fixture
    def jc_base(self):
        """Create a JCBase instance for testing."""
        return JCBase()

    @pytest.mark.parametrize(
        "input_data,expected",
        [
            # String input returns as-is
            ("simple string", "simple string"),
            ("", ""),
            # List input gets joined with newlines
            (["line1", "line2"], "line1\nline2"),
            (["single line"], "single line"),
            ([" line1 ", " line2 "], " line1 \n line2 "),
            ([], ""),
            # Dict input extracts stdout only
            ({"stdout": "test output"}, "test output"),
            ({"stdout_lines": ["line1", "line2"]}, ""),  # Only stdout is used
            (
                {"stdout": "stdout wins", "stdout_lines": ["ignored"]},
                "stdout wins",
            ),
            ({"rc": 0}, ""),
            ({}, ""),
            # Invalid types return empty string
            (42, ""),
            (3.14, ""),
            (None, ""),
            (True, ""),
            (object(), ""),
        ],
    )
    def test_extract_output(self, jc_base, input_data, expected):
        """Test _extract_output handles all input types correctly."""
        result = jc_base._extract_output(input_data)
        assert result == expected

    def test_jc_method_calls_jc_library(self, jc_base):
        """Test that jc method successfully calls the jc library."""
        # Use a complete uname -a output
        uname_output = "Linux hostname 5.10.0 #1 SMP PREEMPT x86_64 GNU/Linux"
        result = jc_base.jc(uname_output, "uname")

        # We just verify it returns a dict and has expected structure
        assert isinstance(result, dict)
        assert "kernel_name" in result
        assert result["kernel_name"] == "Linux"

    def test_jc_invalid_parser_raises_error(self, jc_base):
        """Test that invalid parser name raises AnsibleFilterError."""
        with pytest.raises(AnsibleFilterError) as exc_info:
            jc_base.jc("test data", "invalid_parser_name_xyz")

        assert "jc parser 'invalid_parser_name_xyz' not found" in str(
            exc_info.value
        )

    def test_parse_command_calls_jc(self, jc_base):
        """Test that parse_command is a working alias for jc."""
        uname_output = "Linux hostname 5.10.0 #1 SMP PREEMPT x86_64 GNU/Linux"
        result1 = jc_base.jc(uname_output, "uname")
        result2 = jc_base.parse_command(uname_output, "uname")

        assert result1 == result2

    def test_jc_raw_parameter(self, jc_base):
        """Test that raw parameter is passed to jc.parse."""
        # The raw parameter affects jc's post-processing
        # We just verify it doesn't error
        uname_output = "Linux hostname 5.10.0 #1 SMP PREEMPT x86_64 GNU/Linux"
        result = jc_base.jc(uname_output, "uname", raw=True)
        assert isinstance(result, dict)

    def test_jc_quiet_parameter(self, jc_base):
        """Test that quiet parameter is passed to jc.parse."""
        # The quiet parameter suppresses warnings
        # We just verify it doesn't error
        uname_output = "Linux hostname 5.10.0 #1 SMP PREEMPT x86_64 GNU/Linux"
        result = jc_base.jc(uname_output, "uname", quiet=True)
        assert isinstance(result, dict)


class TestFilterModule:
    """Test FilterModule class."""

    @pytest.fixture
    def filter_module(self):
        """Create a FilterModule instance for testing."""
        return FilterModule()

    def test_filters_returns_correct_dict(self, filter_module):
        """Test that filters() returns a dict with 'jc' key."""
        filters = filter_module.filters()

        assert isinstance(filters, dict)
        assert "jc" in filters
        assert callable(filters["jc"])
        # The filter should be the jc method from JCBase
        assert filters["jc"].__name__ == "jc"

    def test_filter_inherits_from_jcbase(self, filter_module):
        """Test that FilterModule properly inherits from JCBase."""
        assert isinstance(filter_module, JCBase)
        assert hasattr(filter_module, "jc")
        assert hasattr(filter_module, "_extract_output")
        assert hasattr(filter_module, "parse_command")

    @pytest.mark.parametrize(
        "input_data",
        [
            # Test different input formats are handled
            ("Linux hostname 5.10.0 #1 SMP PREEMPT x86_64 GNU/Linux"),
            (["Linux hostname 5.10.0 #1 SMP PREEMPT x86_64 GNU/Linux"]),
            (
                {
                    "stdout": (
                        "Linux hostname 5.10.0 #1 SMP PREEMPT x86_64 GNU/Linux"
                    )
                }
            ),
        ],
    )
    def test_jc_filter_processes_input_types(self, filter_module, input_data):
        """Test that the filter processes different input types."""
        jc_filter = filter_module.filters()["jc"]

        # Don't test parsing result, just that it processes w/o error
        result = jc_filter(input_data, "uname")
        assert result is not None
        assert isinstance(result, dict)

    def test_jc_filter_with_empty_inputs(self, filter_module):
        """Test filter handles empty inputs gracefully."""
        jc_filter = filter_module.filters()["jc"]

        # Empty string should parse to empty result
        result = jc_filter("", "ls")
        assert result == []

        # Empty list should parse to empty result
        result = jc_filter([], "ls")
        assert result == []

        # Dict with empty stdout should parse to empty result
        result = jc_filter({"stdout": ""}, "ls")
        assert result == []
