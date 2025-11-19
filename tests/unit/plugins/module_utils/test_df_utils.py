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

"""Unit tests for df module_utils helpers."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils import df_utils


@pytest.fixture
def sample_entry() -> dict[str, Any]:
    """Provide a jc-style df entry with 1024 byte blocks."""

    return {
        "filesystem": "/dev/sda1",
        "mounted_on": "/",
        "1024_blocks": 2048,
        "used": 512,
    }


def test_parse_df_entry_builds_capacity(sample_entry: dict[str, Any]) -> None:
    """Parse a jc df entry and compute capacity fields."""

    result = df_utils.parse_df_entry(sample_entry)

    assert result["mount"] == "/"
    assert result["source"] == {"path": "/dev/sda1"}
    total = result["capacity"]["total"]
    used = result["capacity"]["used"]
    assert total["bytes"] == 2048 * 1024
    assert used["bytes"] == 512 * 1024
    assert used["percent"] == pytest.approx(25.0)


@pytest.mark.parametrize(
    "entry, error_text",
    [({}, "Empty df entry"), ({"filesystem": "dev"}, "mounted_on")],
)
def test_parse_df_entry_validates_required_fields(
    entry: dict[str, Any], error_text: str
) -> None:
    """Missing required keys raise ValueError with helpful context."""

    with pytest.raises(ValueError, match=error_text):
        df_utils.parse_df_entry(entry)


@pytest.mark.parametrize(
    "parser_return, expected_mounts",
    [
        ([{"filesystem": "tmpfs", "mounted_on": "/tmp"}], ["/tmp"]),
        (
            [
                {"filesystem": "dev", "mounted_on": "/dev"},
                {},
            ],
            ["/dev"],
        ),
    ],
)
def test_parse_df_normalizes_entries(
    parser_return: list[dict[str, Any]], expected_mounts: list[str]
) -> None:
    """parse_df delegates to jc_parse and normalizes each entry."""

    with patch.object(
        df_utils, "jc_parse", return_value=parser_return
    ) as mock_parse:
        result = df_utils.parse_df("df output")

    mock_parse.assert_called_once_with("df", "df output")
    assert [entry["mount"] for entry in result] == expected_mounts


def test_df_accepts_dict_inputs() -> None:
    """df helper should handle registered result dictionaries."""

    parser_return = [
        {"filesystem": "/dev/sda1", "mounted_on": "/"},
    ]
    with patch.object(
        df_utils, "jc_parse", return_value=parser_return
    ) as mock_parse:
        payload = {"stdout": "Filesystem 1024-blocks"}
        result = df_utils.df(payload)

    mock_parse.assert_called_once_with("df", payload)
    assert result[0]["mount"] == "/"


def test_df_skips_invalid_entries() -> None:
    """Invalid jc entries are ignored rather than crashing."""

    with patch.object(
        df_utils,
        "jc_parse",
        return_value=[
            {"filesystem": "dev"},
            {"filesystem": "root", "mounted_on": "/"},
        ],
    ):
        result = df_utils.df("ignored")

    assert len(result) == 1
    assert result[0]["source"] == {"name": "root"}
