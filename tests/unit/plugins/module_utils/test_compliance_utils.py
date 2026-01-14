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

"""Unit tests for compliance_utils module_utils."""

from __future__ import annotations

from ansible_collections.o0_o.posix.plugins.module_utils.compliance_utils import (  # noqa: E501
    SUS,
    POSIX,
    XSH,
    XCU,
    XSI,
)


class TestConstants:
    """Tests for standard metadata constants."""

    def test_sus_metadata(self) -> None:
        """Test SUS constant has required fields."""
        assert SUS["name"] == "Single UNIX Specification"
        assert SUS["abbreviation"] == "SUS"
        assert "description" in SUS

    def test_posix_metadata(self) -> None:
        """Test POSIX constant has required fields."""
        assert POSIX["name"] == "Portable Operating System Interface"
        assert POSIX["abbreviation"] == "POSIX"
        assert "description" in POSIX

    def test_xsh_metadata(self) -> None:
        """Test XSH constant has required fields."""
        assert XSH["abbreviation"] == "XSH"
        assert "name" in XSH

    def test_xcu_metadata(self) -> None:
        """Test XCU constant has required fields."""
        assert XCU["abbreviation"] == "XCU"
        assert "name" in XCU

    def test_xsi_metadata(self) -> None:
        """Test XSI constant has required fields."""
        assert XSI["abbreviation"] == "XSI"
        assert "name" in XSI
