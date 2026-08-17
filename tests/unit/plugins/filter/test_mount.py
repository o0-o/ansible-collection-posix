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

"""Smoke tests for the mount filter wrapper."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from ansible.errors import AnsibleFilterError

from ansible_collections.o0_o.posix.plugins.filter.mount import (
    FilterModule,
)


@pytest.fixture
def filter_module() -> FilterModule:
    """Provide a filter instance per test."""

    return FilterModule()


def test_mount_filter_exposes_helper(
    filter_module: FilterModule,
) -> None:
    """Test that filters() advertises the mount callable."""

    filters = filter_module.filters()
    assert set(filters) == {"mount"}


def test_mount_filter_delegates_to_parse_mount(
    filter_module: FilterModule,
) -> None:
    """Test wrapper calls _parse_mount and returns parsed data."""

    expected = [{"mount": "/proc"}]
    with patch(
        "ansible_collections.o0_o.posix.plugins.filter.mount.mount",
        return_value=expected,
    ) as mock_parse:
        result = filter_module.filters()["mount"]("mount output")

    mock_parse.assert_called_once_with("mount output")
    assert result is expected


def test_mount_filter_raises_on_parse_error(
    filter_module: FilterModule,
) -> None:
    """Test that parse errors become AnsibleFilterError."""

    with patch(
        "ansible_collections.o0_o.posix.plugins.filter.mount.mount",
        side_effect=ValueError("bad output"),
    ):
        with pytest.raises(AnsibleFilterError, match="mount failed"):
            filter_module.filters()["mount"]("broken")


def test_mount_filter_normalizes_dict_input(
    filter_module: FilterModule,
) -> None:
    """Test that dict input passes through to the shared parser."""

    expected = [{"mount": "/"}]
    with patch(
        "ansible_collections.o0_o.posix.plugins.filter.mount.mount",
        return_value=expected,
    ) as mock_parse:
        filter_module.filters()["mount"]({"stdout": "mount output"})

    # Dict extraction lives in mount(), so the dict passes through
    mock_parse.assert_called_once_with({"stdout": "mount output"})
