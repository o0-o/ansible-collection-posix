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

from ansible.errors import AnsibleActionFail


@pytest.mark.parametrize(
    "input_str, expected_lines, expected_content",
    [
        ("foo\nbar\n", ["foo", "bar"], "foo\nbar\n"),
        ("foo\nbar", ["foo", "bar"], "foo\nbar\n"),
        ("", [], "\n"),
    ],
)
def test_normalize_content_string(
    base, input_str, expected_lines, expected_content
) -> None:
    """Test _normalize_content with string input."""
    lines, normalized = base._normalize_content(input_str)
    assert lines == expected_lines
    assert normalized == expected_content


@pytest.mark.parametrize(
    "input_list, expected_lines, expected_content",
    [
        (["foo", "bar"], ["foo", "bar"], "foo\nbar\n"),
        (["foo", 123, 4.56], ["foo", "123", "4.56"], "foo\n123\n4.56\n"),
        ([], [], "\n"),
    ],
)
def test_normalize_content_list(
    base, input_list, expected_lines, expected_content
) -> None:
    """Test _normalize_content with list input."""
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
    ],
)
def test_normalize_content_rejects_invalid_input(
    base, invalid_content
) -> None:
    """Test _normalize_content rejects invalid input types."""
    with pytest.raises(AnsibleActionFail, match="_write_file.*"):
        base._normalize_content(invalid_content)
