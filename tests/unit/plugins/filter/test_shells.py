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

from __future__ import annotations

from typing import Generator
from unittest.mock import patch

import pytest

from ansible.errors import AnsibleFilterError
from ansible_collections.o0_o.posix.plugins.filter.shells import FilterModule


@pytest.fixture
def filter_module() -> Generator[FilterModule, None, None]:
    """Create a FilterModule instance for testing."""
    return FilterModule()


def test_shells_filter_exposes_helper(filter_module: FilterModule) -> None:
    """filters() advertises the shells callable."""
    filters = filter_module.filters()
    assert set(filters) == {"shells"}


def test_shells_filter_delegates_to_helper(
    filter_module: FilterModule,
) -> None:
    """Wrapper returns data from module_utils.parse_shells unchanged."""
    expected = ["/bin/bash", "/bin/zsh"]
    path = "ansible_collections.o0_o.posix.plugins.filter.shells.parse_shells"
    with patch(path, return_value=expected) as mock_parse:
        result = filter_module.filters()["shells"]("/bin/bash\n/bin/zsh\n")
    mock_parse.assert_called_once_with("/bin/bash\n/bin/zsh\n")
    assert result is expected


def test_shells_filter_wraps_exceptions(filter_module: FilterModule) -> None:
    """Filter raises AnsibleFilterError for helper exceptions."""
    path = "ansible_collections.o0_o.posix.plugins.filter.shells.parse_shells"

    with patch(path, side_effect=ValueError("Parse error")):
        with pytest.raises(AnsibleFilterError, match="shells failed"):
            filter_module.filters()["shells"]("invalid")

    with patch(path, side_effect=ImportError("Missing dependency")):
        with pytest.raises(AnsibleFilterError, match="shells failed"):
            filter_module.filters()["shells"]("invalid")
