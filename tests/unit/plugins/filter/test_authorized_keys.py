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

"""Smoke tests for the authorized_keys filter wrapper."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from ansible.errors import AnsibleFilterError

from ansible_collections.o0_o.posix.plugins.filter.authorized_keys import (
    FilterModule,
)
from tests.utils import boom


@pytest.fixture
def filter_module() -> FilterModule:
    """Create a FilterModule instance for testing."""
    return FilterModule()


def test_authorized_keys_filter_exposes_helper(
    filter_module: FilterModule,
) -> None:
    """Test that the filter is properly exposed."""
    filters = filter_module.filters()
    assert set(filters) == {"authorized_keys"}


def test_authorized_keys_filter_delegates(
    filter_module: FilterModule,
) -> None:
    """Test that the filter delegates to authorized_keys function."""
    expected = [{"type": "ssh-rsa", "key": "AAAAB3...", "comment": "test"}]
    with patch(
        "ansible_collections.o0_o.posix.plugins.filter.authorized_keys.authorized_keys",  # noqa: E501
        return_value=expected,
    ) as mock_auth_keys:
        result = filter_module.filters()["authorized_keys"]("contents")

    mock_auth_keys.assert_called_once_with("contents")
    assert result is expected


def test_authorized_keys_filter_wraps_errors(
    filter_module: FilterModule,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that the filter wraps exceptions properly."""
    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.filter.authorized_keys.authorized_keys",  # noqa: E501
        boom(ValueError("invalid key format")),
    )
    with pytest.raises(AnsibleFilterError, match="authorized_keys failed"):
        filter_module.filters()["authorized_keys"]("broken")

    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.filter.authorized_keys.authorized_keys",  # noqa: E501
        boom(Exception("unexpected error")),
    )
    with pytest.raises(AnsibleFilterError, match="authorized_keys failed"):
        filter_module.filters()["authorized_keys"]("broken")


def test_authorized_keys_filter_basic_usage(
    filter_module: FilterModule,
) -> None:
    """Test basic filter usage with real parsing."""
    content = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ user@example.com"
    result = filter_module.filters()["authorized_keys"](content)

    assert len(result) == 1
    assert result[0]["type"] == "ssh-rsa"
    assert result[0]["comment"] == "user@example.com"
