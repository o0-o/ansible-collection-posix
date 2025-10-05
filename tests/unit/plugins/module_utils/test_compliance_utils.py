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

"""Tests for compliance_utils module."""

from __future__ import annotations

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils.compliance_utils import (  # noqa: E501
    is_posix,
)


def test_is_posix_with_xsh_component() -> None:
    """Test is_posix returns True with XSH component."""
    facts = {
        "compliance": {
            "posix": {
                "components": {
                    "xsh": {
                        "version": {"id": "2008", "name": "POSIX.1-2008"}
                    }
                }
            }
        }
    }
    assert is_posix(facts) is True


def test_is_posix_with_xcu_component() -> None:
    """Test is_posix returns True with XCU component."""
    facts = {
        "compliance": {
            "posix": {"components": {"xcu": {"version": {"id": "2008"}}}}
        }
    }
    assert is_posix(facts) is True


def test_is_posix_with_sus() -> None:
    """Test is_posix returns True with SUS compliance."""
    facts = {
        "compliance": {
            "sus": {"version": {"id": 4, "name": "SUSv4"}}
        }
    }
    assert is_posix(facts) is True


def test_is_posix_with_no_compliance() -> None:
    """Test is_posix returns None when compliance key missing."""
    facts = {}
    assert is_posix(facts) is None


def test_is_posix_with_empty_compliance() -> None:
    """Test is_posix returns None with empty compliance dict."""
    facts = {"compliance": {}}
    assert is_posix(facts) is None


def test_is_posix_with_posix_but_no_components() -> None:
    """Test is_posix returns False with POSIX but no components."""
    facts = {"compliance": {"posix": {}}}
    assert is_posix(facts) is False


def test_is_posix_with_invalid_dict() -> None:
    """Test is_posix raises TypeError with non-dict input."""
    with pytest.raises(TypeError, match="requires a dict"):
        is_posix("not a dict")


def test_is_posix_with_none() -> None:
    """Test is_posix raises TypeError with None input."""
    with pytest.raises(TypeError, match="requires a dict"):
        is_posix(None)


def test_is_posix_with_list() -> None:
    """Test is_posix raises TypeError with list input."""
    with pytest.raises(TypeError, match="requires a dict"):
        is_posix([])


def test_is_posix_with_both_xsh_and_xcu() -> None:
    """Test is_posix returns True with both XSH and XCU."""
    facts = {
        "compliance": {
            "posix": {
                "components": {
                    "xsh": {"version": {"id": "2008"}},
                    "xcu": {"version": {"id": "2008"}},
                }
            }
        }
    }
    assert is_posix(facts) is True


def test_is_posix_with_unknown_compliance_keys() -> None:
    """Test is_posix returns None with unrecognized compliance keys."""
    facts = {"compliance": {"unknown": "value"}}
    assert is_posix(facts) is None


def test_is_posix_with_direct_compliance_dict() -> None:
    """Test is_posix works with compliance dict directly."""
    compliance = {
        "posix": {
            "components": {
                "xsh": {"version": {"id": "2008", "name": "POSIX.1-2008"}}
            }
        }
    }
    assert is_posix(compliance) is True


def test_is_posix_with_registered_result() -> None:
    """Test is_posix works with registered result from module."""
    registered_result = {
        "changed": False,
        "msg": "System is POSIX-compliant",
        "compliance": {
            "posix": {
                "components": {
                    "xsh": {"version": {"id": "2008"}},
                    "xcu": {"version": {"id": "2008"}},
                }
            },
            "sus": {"version": {"id": 4, "name": "SUSv4"}},
        },
    }
    assert is_posix(registered_result) is True


def test_is_posix_with_direct_empty_compliance_dict() -> None:
    """Test is_posix returns None with empty compliance dict directly."""
    compliance = {}
    assert is_posix(compliance) is None


def test_is_posix_with_direct_sus_only() -> None:
    """Test is_posix works with SUS in direct compliance dict."""
    compliance = {"sus": {"version": {"id": 4, "name": "SUSv4"}}}
    assert is_posix(compliance) is True
