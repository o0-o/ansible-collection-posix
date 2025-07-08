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

import pytest
from ansible.errors import AnsibleError


@pytest.mark.parametrize(
    "input_str, expected_lines, expected_content",
    [
        ("foo\nbar\n", ["foo", "bar"], "foo\nbar\n"),
        ("foo\nbar", ["foo", "bar"], "foo\nbar\n"),
        ("", [], "\n"),
    ]
)
def test_normalize_content_string(
    base, input_str, expected_lines, expected_content
):
    """
    Verify that string input is split into lines and normalized with
    a trailing newline.
    """
    lines, normalized = base._normalize_content(input_str)
    assert lines == expected_lines
    assert normalized == expected_content


@pytest.mark.parametrize(
    "input_list, expected_lines, expected_content",
    [
        (["foo", "bar"], ["foo", "bar"], "foo\nbar\n"),
        (["foo", 123, 4.56], ["foo", "123", "4.56"], "foo\n123\n4.56\n"),
        ([], [], "\n"),
    ]
)
def test_normalize_content_list(
    base, input_list, expected_lines, expected_content
):
    """
    Verify that list input is coerced to strings and joined with
    newlines, ending with a newline.
    """
    lines, normalized = base._normalize_content(input_list)
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
    ]
)
def test_normalize_content_rejects_invalid_input(base, invalid_content):
    """
    Verify that invalid input types raise an AnsibleError.
    """
    with pytest.raises(AnsibleError, match="_write_file.*"):
        base._normalize_content(invalid_content)
