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

"""Smoke tests for the hosts filter wrapper."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from ansible.errors import AnsibleFilterError

from ansible_collections.o0_o.posix.plugins.filter.hosts import FilterModule
from tests.utils import boom


@pytest.fixture
def filter_module() -> FilterModule:
    """Provide a filter instance per test."""

    return FilterModule()


def test_hosts_filter_exposes_helper(filter_module: FilterModule) -> None:
    """filters() advertises the hosts callable."""

    filters = filter_module.filters()
    assert set(filters) == {"hosts"}


@pytest.mark.parametrize(
    "payload",
    [
        "127.0.0.1 localhost",
        {"content": "127.0.0.1 localhost"},
        [{"address": "127.0.0.1", "hostname": "localhost"}],
    ],
)
def test_hosts_filter_delegates_to_helper(
    filter_module: FilterModule, payload
) -> None:
    """Wrapper returns data from module_utils.hosts unchanged."""

    expected = "result"
    with patch(
        "ansible_collections.o0_o.posix.plugins.filter.hosts.hosts",
        return_value=expected,
    ) as mock_hosts:
        result = filter_module.filters()["hosts"](payload)

    mock_hosts.assert_called_once_with(payload)
    assert result == expected


@pytest.mark.parametrize(
    "exception", [ValueError("bad"), ImportError("missing")]
)
def test_hosts_filter_wraps_exceptions(
    filter_module: FilterModule,
    exception: Exception,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ValueError/ImportError from helper become AnsibleFilterError."""

    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.filter.hosts.hosts",
        boom(exception),
    )
    with pytest.raises(AnsibleFilterError, match="hosts failed"):
        filter_module.filters()["hosts"]("bad input")
