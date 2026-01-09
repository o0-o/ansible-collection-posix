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
    XOPEN_POSIX_VERSION_MAP,
    _normalize_output,
    _parse_posix_standard,
    _parse_xsh_version,
    _parse_xcu_version,
    _parse_xopen_support,
    _parse_xopen_versions,
)


class TestNormalizeOutput:
    """Tests for _normalize_output function."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            (-1, -1),
            ("", -1),
            ("undefined", -1),
            ("200809", "200809"),
            ("1", "1"),
            ("700", "700"),
            (0, 0),
            ("0", "0"),
        ],
    )
    def test_normalizes_unsupported_values(self, value, expected) -> None:
        """Test normalization of various input values."""
        assert _normalize_output(value) == expected


class TestParsePosixStandard:
    """Tests for _parse_posix_standard function."""

    def test_parses_valid_posix_2008(self) -> None:
        """Test parsing POSIX.1-2008 version string."""
        result, errors = _parse_posix_standard("200809", "test: ", "_TEST_VAR")

        assert errors is None
        assert result["supported"] is True
        assert result["version"]["id"] == "2008"
        assert result["version"]["name"] == "POSIX.1-2008"
        assert result["canaries"]["getconf"]["_TEST_VAR"] == "200809"

    def test_parses_valid_posix_2001(self) -> None:
        """Test parsing POSIX.1-2001 version string."""
        result, errors = _parse_posix_standard("200112", "test: ", "_TEST_VAR")

        assert errors is None
        assert result["supported"] is True
        assert result["version"]["id"] == "2001"
        assert result["version"]["name"] == "POSIX.1-2001"

    def test_parses_valid_posix_2024(self) -> None:
        """Test parsing POSIX.1-2024 version string."""
        result, errors = _parse_posix_standard("202406", "test: ", "_TEST_VAR")

        assert errors is None
        assert result["supported"] is True
        assert result["version"]["id"] == "2024"
        assert result["version"]["name"] == "POSIX.1-2024"

    def test_returns_unsupported_for_negative_one(self) -> None:
        """Test that -1 indicates unsupported."""
        result, errors = _parse_posix_standard("-1", "test: ", "_TEST_VAR")

        assert errors is None
        assert result == {"supported": False}

    def test_returns_unsupported_for_empty_string(self) -> None:
        """Test that empty string indicates unsupported."""
        result, errors = _parse_posix_standard("", "test: ", "_TEST_VAR")

        assert errors is None
        assert result == {"supported": False}

    def test_returns_unsupported_for_undefined(self) -> None:
        """Test that 'undefined' indicates unsupported."""
        result, errors = _parse_posix_standard(
            "undefined", "test: ", "_TEST_VAR"
        )

        assert errors is None
        assert result == {"supported": False}

    def test_rejects_non_integer_version(self) -> None:
        """Test error on non-integer version string."""
        result, errors = _parse_posix_standard("abcdef", "test: ", "_TEST_VAR")

        assert result is None
        assert errors is not None
        assert any("integer" in str(e) for e in errors)

    def test_rejects_version_below_199009(self) -> None:
        """Test error on version before first POSIX standard."""
        result, errors = _parse_posix_standard("198901", "test: ", "_TEST_VAR")

        assert result is None
        assert errors is not None
        assert any("199009" in str(e) for e in errors)

    def test_rejects_wrong_length_version(self) -> None:
        """Test error on version string with wrong length."""
        result, errors = _parse_posix_standard("20080", "test: ", "_TEST_VAR")

        assert result is None
        assert errors is not None
        assert any("length of 6" in str(e) for e in errors)

    def test_skips_canary_when_var_is_none(self) -> None:
        """Test that canary is omitted when getconf_var is None."""
        result, errors = _parse_posix_standard("200809", "test: ", None)

        assert errors is None
        assert result["supported"] is True
        assert "canaries" not in result


class TestParseXshVersion:
    """Tests for _parse_xsh_version function."""

    def test_parses_valid_xsh_version(self) -> None:
        """Test parsing valid _POSIX_VERSION output."""
        result, errors = _parse_xsh_version(0, "200809", "test: ")

        assert errors is None
        assert "xsh" in result
        assert result["xsh"]["supported"] is True
        assert result["xsh"]["version"]["id"] == "2008"
        assert (
            result["xsh"]["canaries"]["getconf"]["_POSIX_VERSION"] == "200809"
        )

    def test_returns_none_on_unsupported(self) -> None:
        """Test that unsupported returns dict with xsh unsupported."""
        result, errors = _parse_xsh_version(0, "-1", "test: ")

        assert errors is None
        assert result["xsh"]["supported"] is False

    def test_returns_none_on_invalid(self) -> None:
        """Test that invalid version returns None with errors."""
        result, errors = _parse_xsh_version(0, "invalid", "test: ")

        assert result is None
        assert errors is not None

    def test_ignores_rc(self) -> None:
        """Test that return code is ignored."""
        result1, _ = _parse_xsh_version(0, "200809", "test: ")
        result2, _ = _parse_xsh_version(1, "200809", "test: ")

        assert result1 == result2


class TestParseXcuVersion:
    """Tests for _parse_xcu_version function."""

    def test_parses_valid_xcu_version(self) -> None:
        """Test parsing valid _POSIX2_VERSION output."""
        result, errors = _parse_xcu_version(0, "200809", "test: ")

        assert errors is None
        assert "xcu" in result
        assert result["xcu"]["supported"] is True
        assert result["xcu"]["version"]["id"] == "2008"
        assert (
            result["xcu"]["canaries"]["getconf"]["_POSIX2_VERSION"] == "200809"
        )

    def test_returns_unsupported_for_negative_one(self) -> None:
        """Test that -1 indicates unsupported."""
        result, errors = _parse_xcu_version(0, "-1", "test: ")

        assert errors is None
        assert result["xcu"]["supported"] is False


class TestParseXopenSupport:
    """Tests for _parse_xopen_support function."""

    def test_parses_supported(self) -> None:
        """Test parsing _XOPEN_UNIX = 1 (supported)."""
        result, errors = _parse_xopen_support(0, "1", "test: ")

        assert errors is None
        assert result["xsi"]["supported"] is True
        assert result["xsi"]["canaries"]["getconf"]["_XOPEN_UNIX"] == "1"

    def test_parses_unsupported_negative_one(self) -> None:
        """Test parsing _XOPEN_UNIX = -1 (unsupported)."""
        result, errors = _parse_xopen_support(0, "-1", "test: ")

        assert errors is None
        assert result["xsi"]["supported"] is False

    def test_parses_unsupported_empty(self) -> None:
        """Test parsing _XOPEN_UNIX = '' (unsupported)."""
        result, errors = _parse_xopen_support(0, "", "test: ")

        assert errors is None
        assert result["xsi"]["supported"] is False

    def test_parses_unsupported_undefined(self) -> None:
        """Test parsing _XOPEN_UNIX = 'undefined' (unsupported)."""
        result, errors = _parse_xopen_support(0, "undefined", "test: ")

        assert errors is None
        assert result["xsi"]["supported"] is False

    def test_rejects_invalid_value(self) -> None:
        """Test error on unexpected _XOPEN_UNIX value."""
        result, errors = _parse_xopen_support(0, "2", "test: ")

        assert result is None
        assert errors is not None
        assert any("should be 1" in str(e) for e in errors)


class TestParseXopenVersions:
    """Tests for _parse_xopen_versions function."""

    def test_parses_version_700(self) -> None:
        """Test parsing _XOPEN_VERSION = 700 (SUSv4/Issue 7)."""
        result, errors = _parse_xopen_versions(0, "700", "test: ")

        assert errors is None or errors == []
        assert result["xsi"]["supported"] is True
        assert result["xsi"]["version"]["issue"] == 7.0
        assert result["xsi"]["version"]["pretty"] == "Issue 7.0"
        assert result["xsh"]["supported"] is True
        assert result["xsh"]["version"]["id"] == "2008"
        assert result["xcu"]["supported"] is True
        assert result["xcu"]["version"]["id"] == "2008"

    def test_parses_version_600(self) -> None:
        """Test parsing _XOPEN_VERSION = 600 (SUSv3/Issue 6)."""
        result, errors = _parse_xopen_versions(0, "600", "test: ")

        assert errors is None or errors == []
        assert result["xsi"]["version"]["issue"] == 6.0
        assert result["xsh"]["version"]["id"] == "2001"
        assert result["xcu"]["version"]["id"] == "2001"

    def test_parses_version_800(self) -> None:
        """Test parsing _XOPEN_VERSION = 800 (Issue 8/POSIX.1-2024)."""
        result, errors = _parse_xopen_versions(0, "800", "test: ")

        assert errors is None or errors == []
        assert result["xsi"]["version"]["issue"] == 8.0
        assert result["xsh"]["version"]["id"] == "2024"
        assert result["xcu"]["version"]["id"] == "2024"

    def test_returns_unsupported_for_negative_one(self) -> None:
        """Test that -1 indicates unsupported."""
        result, errors = _parse_xopen_versions(0, "-1", "test: ")

        assert errors is None
        assert result == {"supported": False}

    def test_rejects_unknown_version(self) -> None:
        """Test error on unrecognized X/Open version."""
        result, errors = _parse_xopen_versions(0, "500", "test: ")

        assert result is None
        assert errors is not None
        assert any("Unrecognized" in str(e) for e in errors)

    def test_includes_canaries_for_all_standards(self) -> None:
        """Test that canaries are included for all standards."""
        result, errors = _parse_xopen_versions(0, "700", "test: ")

        assert result["xsi"]["canaries"]["getconf"]["_XOPEN_VERSION"] == "700"
        assert result["xsh"]["canaries"]["getconf"]["_XOPEN_VERSION"] == "700"
        assert result["xcu"]["canaries"]["getconf"]["_XOPEN_VERSION"] == "700"


class TestXopenPosixVersionMap:
    """Tests for XOPEN_POSIX_VERSION_MAP constant."""

    def test_contains_expected_versions(self) -> None:
        """Test that map contains all expected X/Open versions."""
        assert "600" in XOPEN_POSIX_VERSION_MAP
        assert "700" in XOPEN_POSIX_VERSION_MAP
        assert "800" in XOPEN_POSIX_VERSION_MAP

    def test_maps_to_correct_posix_versions(self) -> None:
        """Test that X/Open versions map to correct POSIX versions."""
        assert XOPEN_POSIX_VERSION_MAP["600"] == 200112
        assert XOPEN_POSIX_VERSION_MAP["700"] == 200809
        assert XOPEN_POSIX_VERSION_MAP["800"] == 202406
