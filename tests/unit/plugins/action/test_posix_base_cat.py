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

import pytest

from ansible_collections.o0_o.posix.tests.utils import (
    cleanup_path,
    generate_temp_path,
)


@pytest.mark.parametrize(
    "content, expect_error, expected_output",
    [
        ("hello world\n", False, "hello world\n"),  # simple case
        ("", False, ""),  # empty file
        ("line1\nline2\n", False, "line1\nline2\n"),  # multiple lines
        (None, True, None),  # file does not exist
    ],
)
def test_cat_file_content(base, content, expect_error, expected_output) -> None:
    """Test _cat method file reading with various content scenarios."""
    path = generate_temp_path()

    try:
        if content is not None:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

        base.force_raw = True
        result = base._cat(path)

        if expect_error:
            assert result["failed"] is True
            assert "msg" in result
            assert "No such file" in result["msg"] or "cat" in result["msg"]
        else:
            assert result.get("failed", False) is False
            assert result["changed"] is False
            assert result["source"] == path
            assert result["content"] == expected_output

        # Common postconditions: these keys must not be present
        for forbidden in ("stdout", "stderr", "stdout_lines", "stderr_lines"):
            assert forbidden not in result

    finally:
        cleanup_path(path)
