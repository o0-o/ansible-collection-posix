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

"""Tests for utility methods in PosixActionBase and command_utils."""

from __future__ import annotations

from ansible_collections.o0_o.posix.plugins.module_utils.command_utils import (
    format_command,
)


def test_format_command_string_input() -> None:
    """Test format_command with string input validates and normalizes."""
    result = format_command('echo "hello world"')

    assert result == "echo 'hello world'"


def test_format_command_list_input() -> None:
    """Test format_command with list input quotes properly."""
    result = format_command(["echo", "hello world", "foo"])

    assert result == "echo 'hello world' foo"


def test_format_command_with_special_chars() -> None:
    """Test format_command handles special characters correctly."""
    result = format_command(["echo", "$HOME", "*.txt"])

    assert result == "echo '$HOME' '*.txt'"


def test_format_command_with_integers() -> None:
    """Test format_command handles non-string types like integers."""
    result = format_command(["sleep", 5])

    assert result == "sleep 5"


def test_normalize_newlines_crlf_to_lf(base) -> None:
    """Test _normalize_newlines converts CRLF to LF."""
    input_text = "line1\r\nline2\r\nline3\r\n"
    expected = "line1\nline2\nline3\n"

    result = base._normalize_newlines(input_text)

    assert result == expected


def test_normalize_newlines_preserves_lf(base) -> None:
    """Test _normalize_newlines preserves existing LF."""
    input_text = "line1\nline2\nline3\n"

    result = base._normalize_newlines(input_text)

    assert result == input_text


def test_normalize_newlines_mixed_endings(base) -> None:
    """Test _normalize_newlines handles mixed line endings."""
    input_text = "line1\r\nline2\nline3\r\n"
    expected = "line1\nline2\nline3\n"

    result = base._normalize_newlines(input_text)

    assert result == expected


def test_normalize_newlines_empty_string(base) -> None:
    """Test _normalize_newlines with empty string."""
    result = base._normalize_newlines("")

    assert result == ""


def test_sanitize_args_removes_none_values(base) -> None:
    """Test _sanitize_args removes None values from dictionary."""
    input_args = {
        "name": "test",
        "path": "/tmp/file",
        "state": None,
        "mode": "0644",
        "owner": None,
    }

    result = base._sanitize_args(input_args)

    expected = {
        "name": "test",
        "path": "/tmp/file",
        "mode": "0644",
    }
    assert result == expected


def test_sanitize_args_preserves_false_values(base) -> None:
    """Test _sanitize_args preserves False and 0 values."""
    input_args = {
        "enabled": False,
        "count": 0,
        "name": "",
        "value": None,
    }

    result = base._sanitize_args(input_args)

    expected = {
        "enabled": False,
        "count": 0,
        "name": "",
    }
    assert result == expected


def test_sanitize_args_empty_dict(base) -> None:
    """Test _sanitize_args with empty dictionary."""
    result = base._sanitize_args({})

    assert result == {}


def test_sanitize_args_all_none(base) -> None:
    """Test _sanitize_args when all values are None."""
    input_args = {"a": None, "b": None, "c": None}

    result = base._sanitize_args(input_args)

    assert result == {}


def test_quote_simple_string(base) -> None:
    """Test _quote with simple string."""
    result = base._quote("hello")

    assert result == "'hello'"


def test_quote_string_with_spaces(base) -> None:
    """Test _quote handles strings with spaces."""
    result = base._quote("hello world")

    assert result == "'hello world'"


def test_quote_string_with_special_chars(base) -> None:
    """Test _quote handles special shell characters."""
    result = base._quote("$HOME/*.txt")

    assert result == "'$HOME/*.txt'"


def test_quote_empty_string(base) -> None:
    """Test _quote with empty string."""
    result = base._quote("")

    assert result == "''"


def test_quote_string_with_single_quote(base) -> None:
    """Test _quote handles strings containing single quotes."""
    result = base._quote("it's")

    # shlex.quote escapes single quotes by ending the quote,
    # adding escaped quote, then starting quote again
    assert "it" in result and "s" in result


def test_def_inventory_hostname_from_task_vars(base) -> None:
    """Test _def_inventory_hostname prefers task_vars."""
    task_vars = {"inventory_hostname": "webserver01"}

    result = base._def_inventory_hostname(task_vars)

    assert result == "webserver01"
    assert base.inventory_hostname == "webserver01"


def test_def_inventory_hostname_fallback_to_localhost(base) -> None:
    """Test _def_inventory_hostname returns localhost when not found."""
    result = base._def_inventory_hostname({})

    assert result == "localhost"
    assert base.inventory_hostname == "localhost"


def test_def_inventory_hostname_none_task_vars(base) -> None:
    """Test _def_inventory_hostname handles None task_vars."""
    result = base._def_inventory_hostname(None)

    assert result == "localhost"
    assert base.inventory_hostname == "localhost"


def test_def_inventory_hostname_empty_string(base) -> None:
    """Test _def_inventory_hostname handles empty string in
    task_vars."""
    task_vars = {"inventory_hostname": ""}

    result = base._def_inventory_hostname(task_vars)

    # Empty string is falsy, should fall back to localhost
    assert result == "localhost"
    assert base.inventory_hostname == "localhost"


def test_def_inventory_hostname_from_task_object(monkeypatch, base) -> None:
    """Test _def_inventory_hostname falls back to task object vars."""
    # Don't provide it in task_vars, but set it on the task object
    base._task.vars = {"inventory_hostname": "dbserver01"}

    result = base._def_inventory_hostname({})

    assert result == "dbserver01"
    assert base.inventory_hostname == "dbserver01"
