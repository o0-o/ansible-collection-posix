# -*- mode: python; tab-width: 4; indent-tabs-mode: nil; -*-
# vim: ts=4:sw=4:sts=4:et:ft=python
#
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later
# (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
#
# Copyright (c) 2025 oØ.o (@o0-o)
#
# Unit tests for _normalize_content in PosixBase

from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "input_str, expected_lines, expected_content",
    [
        ("foo\nbar\n", ["foo", "bar"], "foo\nbar\n"),
        # A string is a whole file, so the newline it does not carry is
        # not invented for it
        ("foo\nbar", ["foo", "bar"], "foo\nbar"),
        # Nor is one stripped from a string that carries several
        ("foo\n\n\n", ["foo", "", ""], "foo\n\n\n"),
        ("", [], ""),
        ("\n", [""], "\n"),
    ],
)
def test_normalize_content_string(
    write_base, input_str, expected_lines, expected_content
) -> None:
    """Test a string is normalized byte for byte."""
    lines, normalized = write_base._normalize_content(input_str)
    assert lines == expected_lines
    assert normalized == expected_content


@pytest.mark.parametrize(
    "input_list, expected_lines, expected_content",
    [
        (["foo", "bar"], ["foo", "bar"], "foo\nbar\n"),
        (["foo", 123, 4.56], ["foo", "123", "4.56"], "foo\n123\n4.56\n"),
        # A trailing empty line is a line, and it terminates too
        (["foo", ""], ["foo", ""], "foo\n\n"),
        # An empty list is an empty file, not a blank line
        ([], [], ""),
    ],
)
def test_normalize_content_list(
    write_base, input_list, expected_lines, expected_content
) -> None:
    """Test a list of lines is normalized as POSIX text."""
    lines, normalized = write_base._normalize_content(input_list)
    assert lines == expected_lines
    assert normalized == expected_content


@pytest.mark.parametrize(
    "invalid_content",
    [
        123,
        3.14,
        object(),
        [object()],
        ["valid", object()],
        [{"dict": "nope"}],
    ],
)
def test_normalize_content_rejects_invalid_input(
    write_base, invalid_content
) -> None:
    """Test _normalize_content rejects invalid input types."""
    with pytest.raises(RuntimeError, match="_write_file.*"):
        write_base._normalize_content(invalid_content)
