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

"""Smoke tests for the uname filter wrapper."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from ansible.errors import AnsibleFilterError

from ansible_collections.o0_o.posix.plugins.filter.uname import FilterModule


@pytest.fixture
def filter_module() -> FilterModule:
    """Provide a filter instance per test."""

    return FilterModule()


def test_uname_filter_exposes_helper(
    filter_module: FilterModule,
) -> None:
    """Test that filters() advertises the uname callable."""

    filters = filter_module.filters()
    assert set(filters) == {"uname"}


def test_uname_filter_delegates_to_parse_uname(
    filter_module: FilterModule,
) -> None:
    """Test wrapper calls _parse_uname and returns parsed data."""

    expected = {"kernel": {"name": "linux"}}
    with patch(
        "ansible_collections.o0_o.posix.plugins.filter" ".uname._parse_uname",
        return_value=(expected, []),
    ) as mock_parse:
        result = filter_module.filters()["uname"]("uname -a")

    mock_parse.assert_called_once_with("uname -a", "")
    assert result is expected


def test_uname_filter_raises_on_parse_error(
    filter_module: FilterModule,
) -> None:
    """Test that parse errors become AnsibleFilterError."""

    with patch(
        "ansible_collections.o0_o.posix.plugins.filter" ".uname._parse_uname",
        return_value=(None, [ValueError("bad output")]),
    ):
        with pytest.raises(AnsibleFilterError, match="uname failed"):
            filter_module.filters()["uname"]("broken")


def test_uname_filter_normalizes_list_input(
    filter_module: FilterModule,
) -> None:
    """Test that list input is joined before parsing."""

    expected = {"kernel": {"name": "linux"}}
    with patch(
        "ansible_collections.o0_o.posix.plugins.filter" ".uname._parse_uname",
        return_value=(expected, []),
    ) as mock_parse:
        filter_module.filters()["uname"](["line1", "line2"])

    mock_parse.assert_called_once_with("line1\nline2", "")


def test_uname_filter_normalizes_dict_input(
    filter_module: FilterModule,
) -> None:
    """Test that dict input extracts stdout before parsing."""

    expected = {"kernel": {"name": "linux"}}
    with patch(
        "ansible_collections.o0_o.posix.plugins.filter" ".uname._parse_uname",
        return_value=(expected, []),
    ) as mock_parse:
        filter_module.filters()["uname"]({"stdout": "uname output"})

    mock_parse.assert_called_once_with("uname output", "")
