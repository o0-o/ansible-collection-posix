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

"""Unit tests for group module_utils helpers."""

from __future__ import annotations

from base64 import b64encode
from typing import Any

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils import group_info

GROUP_TEXT = "staff:*:20:root\n"

SAMPLE_GROUPS = [
    {"group_name": "staff", "gid": 20, "members": ["root"]},
    {"group_name": "access_bpf", "gid": 101, "members": []},
    {"group_name": None, "gid": 61, "members": []},
]


@pytest.mark.parametrize("config", [SAMPLE_GROUPS, {"stdout": ""}])
def test_group_info_key_id(
    config: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Numeric keyed result mirrors id filter group structure."""

    if isinstance(config, dict):
        monkeypatch.setattr(
            "ansible_collections.o0_o.posix.plugins.module_utils.group_utils.jc_parse",  # noqa: E501
            lambda parser, data: SAMPLE_GROUPS,
        )

    result = group_info(config, key="id")

    assert result == {
        "20": {"name": "staff", "members": ["root"]},
        "101": {"name": "access_bpf", "members": []},
        "61": {"name": None, "members": []},
    }


def test_group_info_key_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Name keyed result maps to id with fallback for unnamed groups."""

    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.module_utils.group_utils.jc_parse",  # noqa: E501
        lambda parser, data: SAMPLE_GROUPS,
    )

    result = group_info("/etc/group contents", key="name")

    assert result["staff"] == {"id": 20, "members": ["root"]}
    assert result["access_bpf"] == {"id": 101, "members": []}
    assert result["61"] == {"id": 61, "members": []}


def test_group_info_decodes_declared_base64() -> None:
    """Content a read result declares base64 is decoded, not parsed."""

    read_result = {
        "content": b64encode(GROUP_TEXT.encode()).decode(),
        "encoding": "base64",
    }

    assert group_info(read_result, key="id") == {
        "20": {"name": "staff", "members": ["root"]}
    }


def test_group_info_invalid_key() -> None:
    """Invalid key values raise ValueError."""

    with pytest.raises(ValueError, match="Unsupported key"):
        group_info(SAMPLE_GROUPS, key="invalid")


def test_group_info_handles_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty input returns empty mapping."""

    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.module_utils.group_utils.jc_parse",  # noqa: E501
        lambda parser, data: [],
    )

    assert group_info({"stdout": ""}) == {}


def test_group_info_normalizes_string_members(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """String-based member fields are split and trimmed."""

    sample_groups = [
        {"group_name": "docker", "gid": 202, "members": "root,o0-o"},
        {"group_name": "mock", "gid": 203, "members": None, "users": ""},
        {
            "group_name": "build",
            "gid": 204,
            "members": None,
            "users": "ci,build",
        },
    ]

    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.module_utils.group_utils.jc_parse",  # noqa: E501
        lambda parser, data: sample_groups,
    )

    result = group_info("/etc/group", key="id")

    assert result["202"]["members"] == ["root", "o0-o"]
    assert result["203"]["members"] == []
    assert result["204"]["members"] == ["ci", "build"]
