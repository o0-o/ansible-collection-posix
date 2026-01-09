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

"""Unit tests for parsers module_utils."""

from __future__ import annotations

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils.parsers import (
    command_lookup_parser,
)


class TestCommandLookupParser:
    """Tests for command_lookup_parser function."""

    def test_parses_paths(self) -> None:
        """Test parsing command paths from output."""
        output = "/bin/cat\n/usr/bin/grep\n/bin/sh\n"
        result, errors = command_lookup_parser(0, output, "test: ")

        assert errors is None
        assert result["cat"] == "/bin/cat"
        assert result["grep"] == "/usr/bin/grep"
        assert result["sh"] == "/bin/sh"

    def test_parses_builtins(self) -> None:
        """Test parsing shell builtins (no path, just command name)."""
        output = "command\ntest\n[\n"
        result, errors = command_lookup_parser(0, output, "test: ")

        assert errors is None
        assert result["command"] == "command"
        assert result["test"] == "test"
        assert result["["] == "["

    def test_parses_mixed_paths_and_builtins(self) -> None:
        """Test parsing mix of paths and builtins."""
        output = "/bin/cat\ncommand\n/usr/bin/grep\ntest\n"
        result, errors = command_lookup_parser(0, output, "test: ")

        assert errors is None
        assert result["cat"] == "/bin/cat"
        assert result["command"] == "command"
        assert result["grep"] == "/usr/bin/grep"
        assert result["test"] == "test"

    def test_marks_missing_commands_as_none(self) -> None:
        """Test that missing requested commands are set to None."""
        output = "/bin/cat\n"
        requested = {"cat", "grep", "missing_cmd"}
        result, errors = command_lookup_parser(
            0, output, "test: ", requested_commands=requested
        )

        assert result["cat"] == "/bin/cat"
        assert result["grep"] is None
        assert result["missing_cmd"] is None

    def test_reports_unexpected_commands(self) -> None:
        """Test error when output contains unrequested commands."""
        output = "/bin/cat\n/bin/unexpected\n"
        requested = {"cat"}
        result, errors = command_lookup_parser(
            0, output, "test: ", requested_commands=requested
        )

        assert result["cat"] == "/bin/cat"
        assert result["unexpected"] == "/bin/unexpected"
        assert errors is not None
        assert len(errors) == 1
        assert "Unexpected command" in str(errors[0])
        assert "unexpected" in str(errors[0])

    def test_handles_empty_lines_with_error(self) -> None:
        """Test that empty lines generate errors."""
        output = "/bin/cat\n\n/bin/grep\n"
        result, errors = command_lookup_parser(0, output, "test: ")

        assert result["cat"] == "/bin/cat"
        assert result["grep"] == "/bin/grep"
        assert errors is not None
        assert len(errors) == 1
        assert "empty line" in str(errors[0]).lower()

    def test_handles_empty_output(self) -> None:
        """Test parsing empty output."""
        result, errors = command_lookup_parser(0, "", "test: ")

        assert result == {}
        assert errors is None

    def test_handles_whitespace_only_output(self) -> None:
        """Test parsing whitespace-only output."""
        result, errors = command_lookup_parser(0, "   \n  \n", "test: ")

        assert result == {}
        assert errors is None

    def test_strips_whitespace_from_lines(self) -> None:
        """Test that whitespace is stripped from lines."""
        output = "  /bin/cat  \n  command  \n"
        result, errors = command_lookup_parser(0, output, "test: ")

        assert errors is None
        assert result["cat"] == "/bin/cat"
        assert result["command"] == "command"

    def test_handles_deeply_nested_paths(self) -> None:
        """Test parsing deeply nested paths."""
        output = "/usr/local/opt/coreutils/libexec/gnubin/cat\n"
        result, errors = command_lookup_parser(0, output, "test: ")

        assert errors is None
        assert result["cat"] == "/usr/local/opt/coreutils/libexec/gnubin/cat"

    def test_rc_is_ignored(self) -> None:
        """Test that return code parameter is ignored."""
        output = "/bin/cat\n"
        result1, _ = command_lookup_parser(0, output, "test: ")
        result2, _ = command_lookup_parser(1, output, "test: ")
        result3, _ = command_lookup_parser(127, output, "test: ")

        assert result1 == result2 == result3

    @pytest.mark.parametrize(
        "output,expected_cmd,expected_path",
        [
            ("/bin/sh", "sh", "/bin/sh"),
            ("/usr/bin/env", "env", "/usr/bin/env"),
            ("cd", "cd", "cd"),
            ("true", "true", "true"),
        ],
    )
    def test_single_command_variations(
        self, output: str, expected_cmd: str, expected_path: str
    ) -> None:
        """Test parsing various single command outputs."""
        result, errors = command_lookup_parser(0, output, "test: ")

        assert errors is None
        assert result[expected_cmd] == expected_path
