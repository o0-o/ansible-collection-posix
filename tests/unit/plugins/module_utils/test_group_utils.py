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

from typing import Any, Dict

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils import group_info

SAMPLE_GROUPS = [
    {"name": "staff", "gid": 20, "users": ["root"]},
    {"name": "access_bpf", "gid": 101, "users": []},
    {"name": None, "gid": 61, "users": []},
]


@pytest.mark.parametrize("config", [SAMPLE_GROUPS, {"stdout": ""}])
def test_group_info_key_id(config: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Numeric keyed result mirrors id filter group structure."""

    if isinstance(config, dict):
        monkeypatch.setattr(
            "ansible_collections.o0_o.posix.plugins.module_utils.group_utils.jc_parse",
            lambda parser, data: SAMPLE_GROUPS,
        )

    result = group_info(config, key="id")

    assert result == {
        "20": {"name": "staff"},
        "101": {"name": "access_bpf"},
        "61": {"name": None},
    }


def test_group_info_key_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Name keyed result maps to id with fallback for unnamed groups."""

    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.module_utils.group_utils.jc_parse",
        lambda parser, data: SAMPLE_GROUPS,
    )

    result = group_info("/etc/group contents", key="name")

    assert result["staff"] == {"id": 20}
    assert result["access_bpf"] == {"id": 101}
    assert result["61"] == {"id": 61}


def test_group_info_invalid_key() -> None:
    """Invalid key values raise ValueError."""

    with pytest.raises(ValueError, match="Unsupported key"):
        group_info(SAMPLE_GROUPS, key="invalid")


def test_group_info_handles_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty input returns empty mapping."""

    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.module_utils.group_utils.jc_parse",
        lambda parser, data: [],
    )

    assert group_info({"stdout": ""}) == {}
