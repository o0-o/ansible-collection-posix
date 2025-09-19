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
from unittest.mock import patch

from ansible_collections.o0_o.posix.plugins.filter.jc import FilterModule
from ansible.errors import AnsibleFilterError


class TestJCFilter:
    """Test JC filter plugin."""

    @pytest.fixture
    def filter_module(self):
        """Create a FilterModule instance for testing."""
        return FilterModule()

    @patch('ansible_collections.o0_o.posix.plugins.filter.jc.jc_parse')
    def test_jc_filter_with_string_input(self, mock_jc_parse, filter_module):
        """Test jc_filter with string input."""
        mock_jc_parse.return_value = [{"user": "root", "pid": 1}]

        result = filter_module.jc_filter("ps output", "ps")

        mock_jc_parse.assert_called_once_with("ps", "ps output", False, False)
        assert result == [{"user": "root", "pid": 1}]

    @patch('ansible_collections.o0_o.posix.plugins.filter.jc.jc_parse')
    def test_jc_filter_with_list_input(self, mock_jc_parse, filter_module):
        """Test jc_filter with list input (joined with newlines)."""
        mock_jc_parse.return_value = [{"filesystem": "/dev/sda1"}]

        result = filter_module.jc_filter(["line1", "line2"], "df")

        mock_jc_parse.assert_called_once_with("df", "line1\nline2", False, False)
        assert result == [{"filesystem": "/dev/sda1"}]

    @patch('ansible_collections.o0_o.posix.plugins.filter.jc.jc_parse')
    def test_jc_filter_with_dict_input(self, mock_jc_parse, filter_module):
        """Test jc_filter with dict input (command result)."""
        mock_jc_parse.return_value = [{"mount_point": "/"}]

        result = filter_module.jc_filter({"stdout": "mount output"}, "mount")

        mock_jc_parse.assert_called_once_with("mount", {"stdout": "mount output"}, False, False)
        assert result == [{"mount_point": "/"}]

    @patch('ansible_collections.o0_o.posix.plugins.filter.jc.jc_parse')
    def test_jc_filter_with_raw_option(self, mock_jc_parse, filter_module):
        """Test jc_filter with raw=True option."""
        mock_jc_parse.return_value = [{"raw": "data"}]

        result = filter_module.jc_filter("input", "uname", raw=True)

        mock_jc_parse.assert_called_once_with("uname", "input", False, True)
        assert result == [{"raw": "data"}]

    @patch('ansible_collections.o0_o.posix.plugins.filter.jc.jc_parse')
    def test_jc_filter_with_quiet_option(self, mock_jc_parse, filter_module):
        """Test jc_filter with quiet=True option."""
        mock_jc_parse.return_value = {"kernel": "Linux"}

        result = filter_module.jc_filter("input", "uname", quiet=True)

        mock_jc_parse.assert_called_once_with("uname", "input", True, False)
        assert result == {"kernel": "Linux"}

    @patch('ansible_collections.o0_o.posix.plugins.filter.jc.jc_parse')
    def test_jc_filter_error_handling(self, mock_jc_parse, filter_module):
        """Test jc_filter error handling."""
        mock_jc_parse.side_effect = ValueError("Parser not found")

        with pytest.raises(AnsibleFilterError, match="jc failed: ValueError: Parser not found"):
            filter_module.jc_filter("input", "invalid_parser")

    @patch('ansible_collections.o0_o.posix.plugins.filter.jc.jc_parse')
    def test_jc_filter_import_error(self, mock_jc_parse, filter_module):
        """Test jc_filter handles ImportError."""
        mock_jc_parse.side_effect = ImportError("jc not installed")

        with pytest.raises(AnsibleFilterError, match="jc failed: ImportError: jc not installed"):
            filter_module.jc_filter("input", "ps")

    def test_filters_method(self, filter_module):
        """Test that filters() returns the correct filter mapping."""
        filters = filter_module.filters()

        assert "jc" in filters
        assert filters["jc"] == filter_module.jc_filter
