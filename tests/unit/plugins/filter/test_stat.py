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

"""Smoke tests for the stat filter wrapper."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from ansible.errors import AnsibleFilterError

from ansible_collections.o0_o.posix.plugins.filter.stat import FilterModule
from tests.utils import boom


@pytest.fixture
def filter_module() -> FilterModule:
    """Provide a filter instance for tests."""

    return FilterModule()


def test_stat_filter_exposes_helper(filter_module: FilterModule) -> None:
    """filters() advertises the stat callable."""

    filters = filter_module.filters()
    assert set(filters) == {"stat"}


def test_stat_filter_delegates_to_helper(filter_module: FilterModule) -> None:
    """Wrapper returns data from module_utils.stat unchanged."""

    expected = {"exists": True}
    with patch(
        "ansible_collections.o0_o.posix.plugins.filter.stat.stat_helper",
        return_value=expected,
    ) as mock_stat:
        result = filter_module.filters()["stat"]("stat output")

    mock_stat.assert_called_once_with("stat output")
    assert result is expected


@pytest.mark.parametrize("exception", [ValueError("bad"), ImportError("jc")])
def test_stat_filter_wraps_exceptions(
    filter_module: FilterModule,
    exception: Exception,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ValueError/ImportError from helper become AnsibleFilterError."""

    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.filter.stat.stat_helper",
        boom(exception),
    )

    with pytest.raises(AnsibleFilterError, match="stat failed"):
        filter_module.filters()["stat"]("broken output")
