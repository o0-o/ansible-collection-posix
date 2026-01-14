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

"""Unit tests for compliance_parsers module_utils."""

from __future__ import annotations

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils.compliance_parsers import (  # noqa: E501
    _normalize_output,
    _parse_posix_version,
    _parse_xopen_support,
    _parse_xopen_version,
    _parse_sh_test,
)


class TestNormalizeOutput:
    """Tests for _normalize_output function."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            (-1, -1),
            ("-1", -1),
            ("", -1),
            ("undefined", -1),
            ("200809", "200809"),
            ("1", "1"),
            ("700", "700"),
            (0, 0),
            ("0", "0"),
        ],
    )
    def test_normalizes_values(self, value, expected) -> None:
        """Test normalization of various input values."""
        assert _normalize_output(value) == expected


class TestParsePosixVersion:
    """Tests for _parse_posix_version function."""

    def test_parses_valid_posix_2008(self) -> None:
        """Test parsing POSIX.1-2008 version string."""
        result, errors = _parse_posix_version("200809", "test: ")

        assert errors is None
        assert result["supported"] is True
        assert result["version"]["id"] == "2008"
        assert result["version"]["name"] == "POSIX.1-2008"

    def test_parses_valid_posix_2001(self) -> None:
        """Test parsing POSIX.1-2001 version string."""
        result, errors = _parse_posix_version("200112", "test: ")

        assert errors is None
        assert result["supported"] is True
        assert result["version"]["id"] == "2001"
        assert result["version"]["name"] == "POSIX.1-2001"

    def test_parses_valid_posix_2024(self) -> None:
        """Test parsing POSIX.1-2024 version string."""
        result, errors = _parse_posix_version("202406", "test: ")

        assert errors is None
        assert result["supported"] is True
        assert result["version"]["id"] == "2024"
        assert result["version"]["name"] == "POSIX.1-2024"

    def test_returns_unsupported_for_negative_one(self) -> None:
        """Test that -1 indicates unsupported."""
        result, errors = _parse_posix_version("-1", "test: ")

        assert errors is None
        assert result["supported"] is False

    def test_returns_unsupported_for_empty_string(self) -> None:
        """Test that empty string indicates unsupported."""
        result, errors = _parse_posix_version("", "test: ")

        assert errors is None
        assert result["supported"] is False

    def test_returns_unsupported_for_undefined(self) -> None:
        """Test that 'undefined' indicates unsupported."""
        result, errors = _parse_posix_version("undefined", "test: ")

        assert errors is None
        assert result["supported"] is False

    def test_rejects_non_integer_version(self) -> None:
        """Test error on non-integer version string."""
        result, errors = _parse_posix_version("abcdef", "test: ")

        assert result is None
        assert errors is not None
        assert any("integer" in str(e) for e in errors)

    def test_rejects_version_below_199009(self) -> None:
        """Test error on version before first POSIX standard."""
        result, errors = _parse_posix_version("198901", "test: ")

        assert result is None
        assert errors is not None
        assert any("199009" in str(e) for e in errors)

    def test_rejects_wrong_length_version(self) -> None:
        """Test error on version string with wrong length."""
        result, errors = _parse_posix_version("20080", "test: ")

        assert result is None
        assert errors is not None
        assert any("length of 6" in str(e) for e in errors)


class TestParseXopenSupport:
    """Tests for _parse_xopen_support function."""

    def test_parses_supported(self) -> None:
        """Test parsing _XOPEN_UNIX = 1 (supported)."""
        result, errors = _parse_xopen_support("1", "test: ")

        assert errors is None
        assert result["supported"] is True

    def test_parses_unsupported_negative_one(self) -> None:
        """Test parsing _XOPEN_UNIX = -1 (unsupported)."""
        result, errors = _parse_xopen_support("-1", "test: ")

        assert errors is None
        assert result["supported"] is False

    def test_parses_unsupported_empty(self) -> None:
        """Test parsing _XOPEN_UNIX = '' (unsupported)."""
        result, errors = _parse_xopen_support("", "test: ")

        assert errors is None
        assert result["supported"] is False

    def test_parses_unsupported_undefined(self) -> None:
        """Test parsing _XOPEN_UNIX = 'undefined' (unsupported)."""
        result, errors = _parse_xopen_support("undefined", "test: ")

        assert errors is None
        assert result["supported"] is False

    def test_rejects_invalid_value(self) -> None:
        """Test error on unexpected _XOPEN_UNIX value."""
        result, errors = _parse_xopen_support("2", "test: ")

        assert result is None
        assert errors is not None
        assert any("should be 1" in str(e) for e in errors)


class TestParseXopenVersion:
    """Tests for _parse_xopen_version function."""

    def test_parses_version_700(self) -> None:
        """Test parsing _XOPEN_VERSION = 700 (Issue 7)."""
        result, errors = _parse_xopen_version("700", "test: ")

        assert errors == [] or errors is None
        assert result["supported"] is True
        assert result["version"]["issue"] == 7
        assert result["version"]["pretty"] == "Issue 7"

    def test_parses_version_600(self) -> None:
        """Test parsing _XOPEN_VERSION = 600 (Issue 6)."""
        result, errors = _parse_xopen_version("600", "test: ")

        assert errors == [] or errors is None
        assert result["supported"] is True
        assert result["version"]["issue"] == 6
        assert result["version"]["pretty"] == "Issue 6"

    def test_parses_version_800(self) -> None:
        """Test parsing _XOPEN_VERSION = 800 (Issue 8)."""
        result, errors = _parse_xopen_version("800", "test: ")

        assert errors == [] or errors is None
        assert result["supported"] is True
        assert result["version"]["issue"] == 8
        assert result["version"]["pretty"] == "Issue 8"

    def test_returns_unsupported_for_negative_one(self) -> None:
        """Test that -1 indicates unsupported."""
        result, errors = _parse_xopen_version("-1", "test: ")

        assert errors is None
        assert result["supported"] is False

    def test_returns_unsupported_for_empty(self) -> None:
        """Test that empty string indicates unsupported."""
        result, errors = _parse_xopen_version("", "test: ")

        assert errors is None
        assert result["supported"] is False

    def test_rejects_version_below_500(self) -> None:
        """Test error on version below 500."""
        result, errors = _parse_xopen_version("400", "test: ")

        assert result is None
        assert errors is not None
        assert any("500" in str(e) for e in errors)

    def test_rejects_version_not_divisible_by_100(self) -> None:
        """Test error on version not divisible by 100."""
        result, errors = _parse_xopen_version("650", "test: ")

        assert result is None
        assert errors is not None
        assert any("divisible by 100" in str(e) for e in errors)


class TestParseShTest:
    """Tests for _parse_sh_test function."""

    def test_parses_posix_compliant(self) -> None:
        """Test parsing successful POSIX sh test output."""
        result, errors = _parse_sh_test("posix sh", "test: ")

        assert errors is None
        assert result["sh_posix_compliant"] is True

    def test_parses_empty_output_as_non_compliant(self) -> None:
        """Test that empty output indicates non-compliant shell."""
        result, errors = _parse_sh_test("", "test: ")

        assert errors is None
        assert result["sh_posix_compliant"] is False

    def test_rejects_unexpected_output(self) -> None:
        """Test error on unexpected sh test output."""
        result, errors = _parse_sh_test("something else", "test: ")

        assert result["sh_posix_compliant"] is False
        assert errors is not None
        assert any("expected 'posix sh'" in str(e) for e in errors)

    def test_rejects_partial_match(self) -> None:
        """Test that partial matches are rejected."""
        result, errors = _parse_sh_test("posix", "test: ")

        assert result["sh_posix_compliant"] is False
        assert errors is not None

    def test_rejects_extra_whitespace(self) -> None:
        """Test that extra whitespace is rejected."""
        result, errors = _parse_sh_test("posix sh ", "test: ")

        assert result["sh_posix_compliant"] is False
        assert errors is not None

    def test_rejects_newline(self) -> None:
        """Test that trailing newline is rejected."""
        result, errors = _parse_sh_test("posix sh\n", "test: ")

        assert result["sh_posix_compliant"] is False
        assert errors is not None
