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

"""Smoke tests for the group filter wrapper."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from ansible.errors import AnsibleFilterError

from ansible_collections.o0_o.posix.plugins.filter.group import FilterModule
from tests.utils import boom


@pytest.fixture
def filter_module() -> FilterModule:
    return FilterModule()


def test_group_filter_exposes_helper(filter_module: FilterModule) -> None:
    filters = filter_module.filters()
    assert set(filters) == {"group"}


def test_group_filter_delegates(filter_module: FilterModule) -> None:
    expected = {"20": {"name": "staff"}}
    with patch(
        "ansible_collections.o0_o.posix.plugins.filter.group.group_info",
        return_value=expected,
    ) as mock_group:
        result = filter_module.filters()["group"]("contents", key="name")

    mock_group.assert_called_once_with("contents", key="name")
    assert result is expected


def test_group_filter_wraps_errors(
    filter_module: FilterModule,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.filter.group.group_info",
        boom(ValueError("bad")),
    )
    with pytest.raises(AnsibleFilterError, match="group failed"):
        filter_module.filters()["group"]("broken")

    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.filter.group.group_info",
        boom(ImportError("jc")),
    )
    with pytest.raises(AnsibleFilterError, match="group failed"):
        filter_module.filters()["group"]("broken")
