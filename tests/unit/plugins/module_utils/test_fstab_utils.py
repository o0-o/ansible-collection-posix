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

"""Unit tests for fstab module_utils helpers."""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils import fstab_utils


def test_parse_fstab_entry_normalizes_options() -> None:
    """Options become a list of dicts and numeric fields are coerced."""

    entry = {
        "fs_spec": "/dev/sda1",
        "fs_file": "/",
        "fs_vfstype": "ext4",
        "fs_mntops": "defaults,noatime,uid=1000",
        "fs_freq": "1",
        "fs_passno": "2",
    }

    result = fstab_utils.parse_fstab_entry(entry)

    assert result["source"] == "/dev/sda1"
    assert result["mount"] == "/"
    assert result["type"] == "ext4"
    assert result["options"] == [
        {"defaults": True},
        {"noatime": True},
        {"uid": "1000"},
    ]
    assert result["dump"] == 1
    assert result["pass"] == 2


@pytest.mark.parametrize(
    "entry",
    [({},), ({"fs_spec": "dev"},)],
)
def test_parse_fstab_entry_requires_fields(entry: Dict[str, Any]) -> None:
    """Missing required fields raise ValueError."""

    with pytest.raises(ValueError):
        fstab_utils.parse_fstab_entry(entry)


def test_generate_fstab_entry_defaults_for_root() -> None:
    """Root filesystem defaults to pass=1 and dump=0 when unspecified."""

    entry = {
        "source": "/dev/sda1",
        "mount": "/",
        "type": "ext4",
        "options": [{"defaults": True}],
    }

    line = fstab_utils.generate_fstab_entry(entry)
    assert line.split()[-2:] == ["0", "1"]


def test_generate_fstab_entry_special_filesystem_pass_zero() -> None:
    """Non-checkable filesystems get pass value 0."""

    entry = {
        "source": "tmpfs",
        "mount": "/tmp",
        "type": "tmpfs",
        "options": [{"defaults": True}],
    }

    line = fstab_utils.generate_fstab_entry(entry)
    assert line.split()[-2:] == ["0", "0"]


def test_parse_fstab_uses_jc_parse() -> None:
    """parse_fstab delegates to jc_parse and filters invalid entries."""

    jc_return: List[Dict[str, Any]] = [
        {
            "fs_spec": "/dev/sda1",
            "fs_file": "/",
            "fs_vfstype": "ext4",
        },
        {},
    ]

    with patch.object(
        fstab_utils, "jc_parse", return_value=jc_return
    ) as mock_parse:
        result = fstab_utils.parse_fstab("fstab contents")

    mock_parse.assert_called_once_with("fstab", "fstab contents")
    assert len(result) == 1
    assert result[0]["mount"] == "/"


def test_generate_fstab_joins_lines() -> None:
    """generate_fstab produces newline-terminated content."""

    data = [
        {"source": "/dev/sda1", "mount": "/", "type": "ext4"},
        {"source": "swap", "mount": None, "type": "swap"},
    ]

    lines = fstab_utils.generate_fstab(data)
    assert lines.endswith("\n")
    assert lines.count("\n") == 2


def test_fstab_switches_between_parse_and_generate() -> None:
    """Top level helper chooses parsing or generation based on input type."""

    entry = {"source": "/dev/sda1", "mount": "/"}
    generated = fstab_utils.fstab([entry])
    assert generated.strip().startswith("/dev/sda1")

    with patch.object(
        fstab_utils,
        "jc_parse",
        return_value=[{"fs_spec": "/dev/sda1", "fs_file": "/"}],
    ) as mock_parse:
        parsed = fstab_utils.fstab("fstab text")

    mock_parse.assert_called_once_with("fstab", "fstab text")
    assert parsed[0]["mount"] == "/"
