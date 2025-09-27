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

"""Smoke tests for the id filter wrapper."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from ansible.errors import AnsibleFilterError

from ansible_collections.o0_o.posix.plugins.filter.id import FilterModule
from tests.utils import boom


@pytest.fixture
def filter_module() -> FilterModule:
    """Provide a filter instance for tests."""

    return FilterModule()


def test_id_filter_exposes_helper(filter_module: FilterModule) -> None:
    """filters() advertises the id callable."""

    filters = filter_module.filters()
    assert set(filters) == {"id"}


def test_id_filter_delegates_to_helper(filter_module: FilterModule) -> None:
    """Wrapper returns data from module_utils.id_info unchanged."""

    expected = {"users": {}, "groups": {}}
    with patch(
        "ansible_collections.o0_o.posix.plugins.filter.id.id_info",
        return_value=expected,
    ) as mock_id_info:
        result = filter_module.filters()["id"]("id output", key="name")

    mock_id_info.assert_called_once_with("id output", key="name")
    assert result is expected


def test_id_filter_wraps_exceptions(
    filter_module: FilterModule,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ValueError/ImportError from helper become AnsibleFilterError."""

    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.filter.id.id_info",
        boom(ValueError("bad")),
    )

    with pytest.raises(AnsibleFilterError, match="id failed"):
        filter_module.filters()["id"]("broken output")

    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.filter.id.id_info",
        boom(ImportError("jc")),
    )

    with pytest.raises(AnsibleFilterError, match="id failed"):
        filter_module.filters()["id"]("broken output")
