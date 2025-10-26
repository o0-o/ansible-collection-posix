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

"""Tests for uptime filter."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from ansible.errors import AnsibleFilterError

from ansible_collections.o0_o.posix.plugins.filter.uptime import FilterModule


@pytest.fixture(name="filter_module")
def fixture_filter_module() -> FilterModule:
    return FilterModule()


def test_uptime_filter_exposes_helper(filter_module: FilterModule) -> None:
    assert set(filter_module.filters()) == {"uptime"}


def test_uptime_filter_success(filter_module: FilterModule) -> None:
    output = (
        "15:41:26 up 3 days,  2:03,  2 users,  load average: 0.81, 0.72, 0.69"
    )

    result = filter_module.uptime_filter(output)

    assert "uptime" in result
    assert result["load"]["1"] == pytest.approx(0.81)
    assert result["login_sessions"] >= 0


def test_uptime_filter_wraps_exceptions(filter_module: FilterModule) -> None:
    with patch(
        "ansible_collections.o0_o.posix.plugins.filter.uptime.parse_uptime",
        side_effect=ValueError("bad"),
    ):
        with pytest.raises(AnsibleFilterError, match="uptime failed"):
            filter_module.uptime_filter("broken")
