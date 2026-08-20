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

"""Unit tests for ReadPosixActionBase content and xattr encoding."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

try:
    from ansible_collections.o0_o.posix.plugins.module_utils.read_posix_action_base import (  # type: ignore  # noqa: E501
        ReadPosixActionBase,
    )
except ModuleNotFoundError:  # pragma: no cover - ansible missing in tests
    ReadPosixActionBase = None  # type: ignore

pytestmark = pytest.mark.skipif(
    ReadPosixActionBase is None, reason="ansible package is required"
)


class DummyReadAction(ReadPosixActionBase):
    """Minimal ReadPosixActionBase subclass with no Ansible plumbing."""

    def __init__(self) -> None:
        self.inventory_hostname = "testhost"


@pytest.fixture
def action() -> DummyReadAction:
    """Provide a bare ReadPosixActionBase instance per test."""
    return DummyReadAction()


@pytest.fixture
def sample() -> Callable[[str], str]:
    """Read a sample tool capture from the files directory.

    The sample under files/ is constructed to match the documented
    hex dump layout of xattr -lx. It was written by hand, not
    captured from a live host.
    """

    def _read(name: str) -> str:
        return (Path(__file__).parent / "files" / name).read_text()

    return _read


class TestIsBinaryValue:
    """Tests for _is_binary_value."""

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "hello",
            "hello\tworld\n",
            "line1\r\nline2",
            "café",
            "naïve résumé",
            "日本語",
        ],
    )
    def test_text_values_are_not_binary(self, action, value) -> None:
        """Test printable text and common whitespace pass as text."""
        assert action._is_binary_value(value) is False

    @pytest.mark.parametrize(
        "value",
        [
            "\x00",
            "\x01abc",
            "\x1b[0m",
            "\x7f",
            "\x80",
            "\x9f",
            "\udc80",
            "\udcff",
            "text\x00more",
        ],
    )
    def test_control_and_surrogate_values_are_binary(
        self, action, value
    ) -> None:
        """Test control and surrogate codepoints read as binary."""
        assert action._is_binary_value(value) is True

    def test_a0_is_not_binary(self, action) -> None:
        """Test U+00A0 sits just past the flagged C1 control range."""
        assert action._is_binary_value("\xa0") is False


class TestEncodeXattrValue:
    """Tests for _encode_xattr_value."""

    @pytest.mark.parametrize(
        "value",
        ["", "plain text", "com.apple.quarantine", "café"],
    )
    def test_text_values_pass_through_as_utf8(self, action, value) -> None:
        """Test text values are returned verbatim as utf-8."""
        assert action._encode_xattr_value(value) == {
            "encoding": "utf-8",
            "value": value,
        }

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("\x00\x01", "AAE="),
            ("\udcff", "/w=="),
            ("\udc80\udcff", "gP8="),
            ("\x80", "woA="),
        ],
    )
    def test_binary_values_are_base64_encoded(
        self, action, value, expected
    ) -> None:
        """Test binary values round trip through surrogateescape."""
        assert action._encode_xattr_value(value) == {
            "encoding": "base64",
            "value": expected,
        }

    def test_unencodable_surrogate_falls_back_to_utf8(self, action) -> None:
        """Test a lone high surrogate falls back to the raw value."""
        value = "\x00\ud800"

        assert action._encode_xattr_value(value) == {
            "encoding": "utf-8",
            "value": value,
        }


class TestParseMacosHexDump:
    """Tests for _parse_macos_hex_dump."""

    def test_full_dump(self, action, sample) -> None:
        """Test a complete xattr -lx dump decodes to its bytes."""
        lines = sample("xattr_macos_hex_dump.txt").splitlines()

        assert action._parse_macos_hex_dump(lines) == (
            b"bplist00\xa1\x01UGreen\x08\n"
            b"\x00\x00\x00\x00\x00\x00\x01\x01"
            b"\x00\x00\x00\x00\x00\x00\x00\x10"
        )

    def test_empty_input(self, action) -> None:
        """Test no lines decode to no bytes."""
        assert action._parse_macos_hex_dump([]) == b""

    @pytest.mark.parametrize("lines", [[""], ["   "], ["00000010"]])
    def test_blank_and_offset_only_lines(self, action, lines) -> None:
        """Test blank lines and the trailing offset line are skipped."""
        assert action._parse_macos_hex_dump(lines) == b""

    def test_single_space_separator_is_not_parsed(self, action) -> None:
        """Test a dump without the double space yields no bytes."""
        assert action._parse_macos_hex_dump(["00000000 41 42 43"]) == b""

    def test_truncated_ascii_column(self, action) -> None:
        """Test a dump line with no ASCII column still decodes."""
        assert (
            action._parse_macos_hex_dump(["00000000  41 42 43 44"]) == b"ABCD"
        )

    def test_odd_length_and_invalid_hex_tokens_are_dropped(
        self, action
    ) -> None:
        """Test single digit and non-hex tokens are skipped silently."""
        line = "00000000  41 4 42 ZZ 43  |A.B.C|"

        assert action._parse_macos_hex_dump([line]) == b"ABC"

    def test_unpiped_ascii_column_contributes_no_bytes(self, action) -> None:
        """Test an ASCII column with no pipes adds no spurious bytes."""
        line = (
            "00000000  41 42 43 44 45 46 47 48  "
            "49 4A 4B 4C 4D 4E 4F 50  ABCDEFGHIJKLMNOP"
        )

        assert action._parse_macos_hex_dump([line]) == b"ABCDEFGHIJKLMNOP"

    def test_lowercase_hex_is_accepted(self, action) -> None:
        """Test lowercase hex digits decode the same as uppercase."""
        assert action._parse_macos_hex_dump(["00000000  ca fe"]) == b"\xca\xfe"


class TestAddContentWithEncoding:
    """Tests for _add_content_with_encoding."""

    def test_text_content_and_lines(self, action) -> None:
        """Test a text encoding fills content, lines and encoding."""
        attributes = {}

        action._add_content_with_encoding(
            attributes,
            "hello\r\nworld\r\n",
            "utf-8",
            "/tmp/f",
            {"content": True, "lines": True},
        )

        assert attributes == {
            "encoding": "utf-8",
            "content": "hello\nworld\n",
            "lines": ["hello", "world"],
        }

    def test_carriage_returns_are_stripped_everywhere(self, action) -> None:
        """Test every carriage return is removed, not just line ends."""
        attributes = {}

        action._add_content_with_encoding(
            attributes,
            "a\rb",
            "utf-8",
            "/tmp/f",
            {"content": True, "lines": True},
        )

        assert attributes["content"] == "ab"
        assert attributes["lines"] == ["ab"]

    def test_content_only_omits_lines(self, action) -> None:
        """Test lines is absent when only content was requested."""
        attributes = {}

        action._add_content_with_encoding(
            attributes, "a\nb\n", "utf-8", "/tmp/f", {"content": True}
        )

        assert attributes == {"encoding": "utf-8", "content": "a\nb\n"}

    def test_lines_only_omits_content(self, action) -> None:
        """Test content is absent when only lines were requested."""
        attributes = {}

        action._add_content_with_encoding(
            attributes, "a\nb\n", "utf-8", "/tmp/f", {"lines": True}
        )

        assert attributes == {"encoding": "utf-8", "lines": ["a", "b"]}

    def test_neither_flag_records_encoding_only(self, action) -> None:
        """Test a successful decode always records the encoding."""
        attributes = {}

        action._add_content_with_encoding(
            attributes, "a\nb\n", "utf-8", "/tmp/f", {}
        )

        assert attributes == {"encoding": "utf-8"}

    @pytest.mark.parametrize(
        "encoding,expected",
        [
            ("hex", "hex"),
            ("base64", "base64"),
            ("binary", "base64"),
            ("unknown", "base64"),
        ],
    )
    def test_nontext_without_content_records_encoding_only(
        self, action, encoding, expected
    ) -> None:
        """Test non-text encodings honor the content flag like text."""
        attributes = {}

        action._add_content_with_encoding(
            attributes, "hi", encoding, "/tmp/f", {}
        )

        assert attributes == {"encoding": expected}

    def test_fallback_without_content_records_encoding_only(
        self, action
    ) -> None:
        """Test the base64 fallback also honors the content flag."""
        attributes = {}

        action._add_content_with_encoding(
            attributes, "café", "us-ascii", "/tmp/f", {}
        )

        assert attributes == {"encoding": "base64"}

    def test_empty_content(self, action) -> None:
        """Test an empty file yields empty content and no lines."""
        attributes = {}

        action._add_content_with_encoding(
            attributes,
            "",
            "utf-8",
            "/tmp/f",
            {"content": True, "lines": True},
        )

        assert attributes == {
            "encoding": "utf-8",
            "content": "",
            "lines": [],
        }

    def test_latin1_content_decodes_from_surrogates(self, action) -> None:
        """Test surrogate escaped bytes decode under iso-8859-1."""
        attributes = {}

        action._add_content_with_encoding(
            attributes,
            "caf\udce9",
            "iso-8859-1",
            "/tmp/f",
            {"content": True},
        )

        assert attributes == {
            "encoding": "iso-8859-1",
            "content": "café",
        }

    def test_hex_encoding(self, action) -> None:
        """Test the hex encoding emits a hex string."""
        attributes = {}

        action._add_content_with_encoding(
            attributes, "hi", "hex", "/tmp/f", {"content": True}
        )

        assert attributes == {"encoding": "hex", "content": "6869"}

    @pytest.mark.parametrize(
        "encoding", ["base64", "binary", "unknown", "UNKNOWN", "Base64"]
    )
    def test_binary_encodings_emit_base64(self, action, encoding) -> None:
        """Test binary style encodings all report base64 content."""
        attributes = {}

        action._add_content_with_encoding(
            attributes, "hi", encoding, "/tmp/f", {"content": True}
        )

        assert attributes == {"encoding": "base64", "content": "aGk="}

    def test_surrogate_bytes_are_base64_encoded(self, action) -> None:
        """Test surrogate escaped bytes survive base64 encoding."""
        attributes = {}

        action._add_content_with_encoding(
            attributes,
            "\udcff\udcfe",
            "binary",
            "/tmp/f",
            {"content": True},
        )

        assert attributes == {"encoding": "base64", "content": "//4="}

    @pytest.mark.parametrize(
        "encoding", ["hex", "base64", "binary", "unknown"]
    )
    def test_lines_with_binary_encoding_raises(self, action, encoding) -> None:
        """Test asking for lines with a binary encoding is rejected."""
        attributes = {}

        with pytest.raises(ValueError, match="Cannot split binary content"):
            action._add_content_with_encoding(
                attributes, "hi", encoding, "/tmp/f", {"lines": True}
            )

        assert attributes == {}

    def test_forced_encoding_decode_failure_raises(self, action) -> None:
        """Test a forced encoding that cannot decode raises."""
        attributes = {}

        with pytest.raises(RuntimeError, match="forced encoding 'us-ascii'"):
            action._add_content_with_encoding(
                attributes,
                "café",
                "us-ascii",
                "/tmp/f",
                {"content": True},
                forced=True,
            )

        assert attributes == {}

    def test_forced_unknown_codec_raises(self, action) -> None:
        """Test a forced codec name that does not exist raises."""
        attributes = {}

        with pytest.raises(RuntimeError, match="forced encoding"):
            action._add_content_with_encoding(
                attributes,
                "hi",
                "not-a-codec",
                "/tmp/f",
                {"content": True},
                forced=True,
            )

    def test_autodetected_decode_failure_falls_back_to_base64(
        self, action
    ) -> None:
        """Test an auto-detected encoding that fails becomes base64."""
        attributes = {}

        action._add_content_with_encoding(
            attributes, "café", "us-ascii", "/tmp/f", {"content": True}
        )

        assert attributes == {"encoding": "base64", "content": "Y2Fmw6k="}

    def test_autodetected_unknown_codec_falls_back_to_base64(
        self, action
    ) -> None:
        """Test an unknown auto-detected codec also becomes base64."""
        attributes = {}

        action._add_content_with_encoding(
            attributes, "hi", "not-a-codec", "/tmp/f", {"content": True}
        )

        assert attributes == {"encoding": "base64", "content": "aGk="}

    def test_autodetected_fallback_with_lines_raises_without_mutating(
        self, action
    ) -> None:
        """Test the lines rejection leaves attributes untouched."""
        attributes = {}

        with pytest.raises(ValueError, match="Auto-detected encoding"):
            action._add_content_with_encoding(
                attributes,
                "café",
                "us-ascii",
                "/tmp/f",
                {"content": True, "lines": True},
            )

        # A caller that catches must never see half-written state
        assert attributes == {}

    def test_unencodable_content_raises_runtime_error(self, action) -> None:
        """Test a lone high surrogate fails before any encoding runs."""
        attributes = {}

        with pytest.raises(RuntimeError, match="Failed to process content"):
            action._add_content_with_encoding(
                attributes,
                "\ud800",
                "utf-8",
                "/tmp/f",
                {"content": True},
            )

        assert attributes == {}
