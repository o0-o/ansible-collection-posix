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

"""Smoke tests for the df filter wrapper."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from ansible.errors import AnsibleFilterError

from ansible_collections.o0_o.posix.plugins.filter.df import FilterModule


@pytest.fixture
def filter_module() -> FilterModule:
    """Provide a filter instance per test."""

    return FilterModule()


def test_df_filter_exposes_helper(filter_module: FilterModule) -> None:
    """filters() advertises the df callable."""

    filters = filter_module.filters()
    assert set(filters) == {"df"}


def test_df_filter_delegates_to_helper(filter_module: FilterModule) -> None:
    """Wrapper returns data from module_utils.df unchanged."""

    expected = [{"mount": "/", "source": "/dev/sda1"}]
    with patch(
        "ansible_collections.o0_o.posix.plugins.filter.df.df",
        return_value=expected,
    ) as mock_df:
        result = filter_module.filters()["df"]("df output")

    mock_df.assert_called_once_with("df output")
    assert result is expected


@pytest.mark.parametrize(
    "exception", [ValueError("bad"), ImportError("missing")]
)
def test_df_filter_wraps_exceptions(
    filter_module: FilterModule, exception: Exception
) -> None:
    """ValueError/ImportError from helper become AnsibleFilterError."""

    with patch(
        "ansible_collections.o0_o.posix.plugins.filter.df.df",
        side_effect=exception,
    ):
        with pytest.raises(AnsibleFilterError, match="df failed"):
            filter_module.filters()["df"]("broken")
