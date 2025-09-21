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

from ansible_collections.o0_o.posix.plugins.filter.mount import FilterModule


@pytest.fixture
def filter_module() -> FilterModule:
    """Provide a filter instance per test."""

    return FilterModule()


def test_mount_filter_exposes_helper(filter_module: FilterModule) -> None:
    """filters() advertises the mount callable."""

    filters = filter_module.filters()
    assert set(filters) == {"mount"}


def test_mount_filter_delegates_to_helper(filter_module: FilterModule) -> None:
    """Wrapper returns data from module_utils.mount unchanged."""

    expected = [{"mount": "/proc"}]
    with patch(
        "ansible_collections.o0_o.posix.plugins.filter.mount.mount",
        return_value=expected,
    ) as mock_mount:
        result = filter_module.filters()["mount"]("mount output")

    mock_mount.assert_called_once_with("mount output")
    assert result is expected


@pytest.mark.parametrize(
    "exception", [ValueError("bad"), ImportError("missing")]
)
def test_mount_filter_wraps_exceptions(
    filter_module: FilterModule, exception: Exception
) -> None:
    """ValueError/ImportError from helper become AnsibleFilterError."""

    with patch(
        "ansible_collections.o0_o.posix.plugins.filter.mount.mount",
        side_effect=exception,
    ):
        with pytest.raises(AnsibleFilterError, match="mount failed"):
            filter_module.filters()["mount"]("broken")
