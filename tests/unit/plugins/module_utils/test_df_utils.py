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

from pathlib import Path
from typing import Any, Callable
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


@pytest.fixture
def capture() -> Callable[[str], str]:
    """Read a df capture from the files directory.

    df_busybox_hash_filesystem.txt is a verbatim capture of busybox
    df -P from an alpine:3.21 container carrying a podman bind mount,
    whose filesystem field is a bare 36 character container layer hash.
    """

    def _read(name: str) -> str:
        return (Path(__file__).parent / "files" / name).read_text()

    return _read


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

    # df() extracts stdout from dict input before parsing
    mock_parse.assert_called_once_with("df", payload["stdout"])
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


def test_parse_df_reads_every_busybox_row(
    capture: Callable[[str], str],
) -> None:
    """A busybox capture parses whole, rows overflowing columns too."""

    entries = df_utils.parse_df(capture("df_busybox_hash_filesystem.txt"))

    assert len(entries) == 24
    assert all(entry["mount"].startswith("/") for entry in entries)


def test_parse_df_places_a_hash_filesystem(
    capture: Callable[[str], str],
) -> None:
    """A filesystem name too wide for its column keeps its own fields."""

    entries = df_utils.parse_df(capture("df_busybox_hash_filesystem.txt"))
    entry = entries[0]

    assert entry["mount"] == "/distro-job.sh"
    assert entry["source"] == {"name": "a2a0ee2c717462feb1de2f5afd59de5fd2d8"}
    assert entry["capacity"]["total"]["bytes"] == 3902665360 * 1024
    assert entry["capacity"]["used"]["bytes"] == 1559751756 * 1024
    assert entry["capacity"]["used"]["percent"] == pytest.approx(39.97)


def test_parse_df_recovers_a_swallowed_mount_point(
    capture: Callable[[str], str],
) -> None:
    """A capacity too wide for its column no longer eats the mount."""

    entries = df_utils.parse_df(capture("df_busybox_hash_filesystem.txt"))
    roots = [entry for entry in entries if entry["mount"] == "/"]

    assert len(roots) == 1
    assert roots[0]["source"] == {"name": "overlay"}


def test_realign_df_leaves_a_placed_table_alone() -> None:
    """jc's positional read stands where it places every field."""

    content = (
        "Filesystem     1024-blocks     Used Available Capacity Mounted on\n"
        "/dev/sda1         41922560  8100224  31678976      21% /\n"
        "tmpfs               398080      372    397708       1% /run\n"
    )

    assert df_utils._realign_df(content) is None


def test_realign_df_keeps_a_field_holding_a_space() -> None:
    """A rebuilt table preserves a field jc read across a space."""

    content = (
        "Filesystem     512-blocks      Used Available Capacity iused"
        "      ifree %iused  Mounted on\n"
        "map auto_home           0         0         0   100%       0"
        "          0  100%   /System/Volumes/Data/home\n"
        "/dev/disk4s7s1verylongname 1942700360  22456720 505802096"
        "     5%  502137 2529010480    0%   /Volumes/Extra\n"
    )

    entries = df_utils.parse_df(content)

    assert [entry["source"] for entry in entries] == [
        {"map": "auto_home"},
        {"path": "/dev/disk4s7s1verylongname"},
    ]


def test_realign_df_refuses_a_row_it_cannot_split() -> None:
    """A row short of the header's columns raises, quoted verbatim."""

    content = (
        "Filesystem     1024-blocks     Used Available Capacity Mounted on\n"
        "a2a0ee2c717462feb1de2f5afd59de5fd2d8   3902665360 1559751756"
        "  40% /distro-job.sh\n"
    )

    with pytest.raises(ValueError, match="Unparseable df row"):
        df_utils.parse_df(content)
