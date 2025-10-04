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

"""Smoke tests for the passwd filter wrapper."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from ansible.errors import AnsibleFilterError

from ansible_collections.o0_o.posix.plugins.filter.passwd import FilterModule
from tests.utils import boom


@pytest.fixture
def filter_module() -> FilterModule:
    return FilterModule()


def test_passwd_filter_exposes_helper(filter_module: FilterModule) -> None:
    filters = filter_module.filters()
    assert set(filters) == {"passwd"}


def test_passwd_filter_delegates(filter_module: FilterModule) -> None:
    expected = {"1000": {"name": "o0-o"}}
    with patch(
        "ansible_collections.o0_o.posix.plugins.filter.passwd.passwd_info",
        return_value=expected,
    ) as mock_passwd:
        result = filter_module.filters()["passwd"]("contents", key="name")

    mock_passwd.assert_called_once_with("contents", key="name")
    assert result is expected


def test_passwd_filter_wraps_errors(
    filter_module: FilterModule,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.filter.passwd.passwd_info",
        boom(ValueError("bad")),
    )
    with pytest.raises(AnsibleFilterError, match="passwd failed"):
        filter_module.filters()["passwd"]("broken")

    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.filter.passwd.passwd_info",
        boom(ImportError("jc")),
    )
    with pytest.raises(AnsibleFilterError, match="passwd failed"):
        filter_module.filters()["passwd"]("broken")

