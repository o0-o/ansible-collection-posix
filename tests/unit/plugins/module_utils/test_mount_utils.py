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

"""Unit tests for mount module_utils helpers."""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils import mount_utils
from ansible_collections.o0_o.posix.plugins.module_utils.mount_utils import (
    normalize_mount_options,
)


@pytest.mark.parametrize(
    "input_options,expected",
    [
        # Standard no* options become boolean False
        ({"noexec": True}, {"exec": False}),
        ({"nosuid": True}, {"suid": False}),
        ({"nodev": True}, {"dev": False}),
        ({"noatime": True}, {"atime": False}),
        # Positive options become boolean True
        ({"exec": True}, {"exec": True}),
        ({"suid": True}, {"suid": True}),
        ({"dev": True}, {"dev": True}),
        # rw/ro special mapping to writable
        ({"rw": True}, {"writable": True}),
        ({"ro": True}, {"writable": False}),
        # sync/async mapping
        ({"sync": True}, {"sync": True}),
        ({"async": True}, {"sync": False}),
        # NFS hard/soft mapping
        ({"hard": True}, {"hard": True}),
        ({"soft": True}, {"hard": False}),
        # Options with values stay as-is
        ({"errors": "remount-ro"}, {"errors": "remount-ro"}),
        ({"uid": "1000"}, {"uid": "1000"}),
        # Unknown options default to boolean True
        ({"wsync": True}, {"wsync": True}),
        ({"journaled": True}, {"journaled": True}),
        ({"local": True}, {"local": True}),
        # Mixed options
        (
            {
                "rw": True,
                "noexec": True,
                "relatime": True,
                "errors": "remount-ro",
            },
            {
                "writable": True,
                "exec": False,
                "relatime": True,
                "errors": "remount-ro",
            },
        ),
    ],
)
def test_normalize_mount_options(
    input_options: Dict[str, Any], expected: Dict[str, Any]
) -> None:
    """Test mount option normalization to consistent boolean format."""
    result = normalize_mount_options(input_options)
    assert result == expected


def test_parse_mount_entry_linux() -> None:
    """Linux style entries expose explicit type and options."""

    entry = {
        "filesystem": "/dev/sda1",
        "mount_point": "/",
        "type": "ext4",
        "options": ["rw", "relatime", "errors=remount-ro"],
    }

    result = mount_utils.parse_mount_entry(entry)

    assert result == {
        "source": "/dev/sda1",
        "mount": "/",
        "type": "ext4",
        "options": {
            "writable": True,  # rw normalized to writable=True
            "relatime": True,
            "errors": "remount-ro",
        },
    }


def test_parse_mount_entry_macos_type_from_options() -> None:
    """First option becomes filesystem type when type field is missing."""

    entry = {
        "filesystem": "/dev/disk1",
        "mount_point": "/",
        "options": ["apfs", "local", "journaled"],
    }

    result = mount_utils.parse_mount_entry(entry)

    assert result["type"] == "apfs"
    assert result["options"]["local"] is True
    assert result["options"]["journaled"] is True


def test_parse_mount_entry_rejects_non_string_options() -> None:
    """Non-string options trigger a TypeError to guard unexpected data."""

    entry = {
        "filesystem": "proc",
        "mount_point": "/proc",
        "options": ["tmpfs", 123],
    }

    with pytest.raises(TypeError, match="Expected string option"):
        mount_utils.parse_mount_entry(entry)


@pytest.mark.parametrize(
    "entry, error_text",
    [({}, "Empty mount entry"), ({"filesystem": "root"}, "mount_point")],
)
def test_parse_mount_entry_requires_fields(
    entry: Dict[str, Any], error_text: str
) -> None:
    """Missing required keys result in ValueError with context."""

    with pytest.raises(ValueError, match=error_text):
        mount_utils.parse_mount_entry(entry)


def test_parse_mount_normalizes_each_entry() -> None:
    """parse_mount leverages jc_parse then normalizes entries."""

    jc_output: List[Dict[str, Any]] = [
        {
            "filesystem": "proc",
            "mount_point": "/proc",
            "options": ["proc", "rw"],
        },
        {},
    ]

    with patch.object(
        mount_utils, "jc_parse", return_value=jc_output
    ) as mock_parse:
        result = mount_utils.parse_mount("mount output")

    mock_parse.assert_called_once_with("mount", "mount output")
    assert len(result) == 1
    assert result[0]["mount"] == "/proc"
    assert result[0]["options"]["writable"] is True  # rw normalized


def test_mount_handles_dict_input() -> None:
    """Top level mount helper accepts registered result dictionaries."""

    jc_return = [{"filesystem": "dev", "mount_point": "/dev"}]
    with patch.object(
        mount_utils, "jc_parse", return_value=jc_return
    ) as mock_parse:
        payload = {"stdout": "dev on /dev type tmpfs (rw)"}
        result = mount_utils.mount(payload)

    mock_parse.assert_called_once_with("mount", payload)
    assert result[0]["mount"] == "/dev"
