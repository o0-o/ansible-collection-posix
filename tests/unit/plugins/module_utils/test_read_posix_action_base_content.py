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


class TestProcessXattrs:
    """Tests for _process_xattrs, and for the empty value it publishes.

    A zero-length xattr is legal and common: one carried as a flag has
    no value by design. macOS prints such an attribute as its key line
    followed by a bare end offset, with no dump between them, so both
    the missing dump and the empty bytes it parses to are answers.
    """

    # As xattr -lx prints a file carrying one empty attribute and one
    # with a value. The layout is the documented one; the trailing
    # offset line closes each dump.
    MACOS_LX = (
        "com.o0o.emptyflag:\n"
        "00000000\n"
        "com.o0o.hasvalue:\n"
        "00000000  68 65 6C 6C 6F                    |hello|\n"
        "00000005\n"
    )

    def test_a_zero_length_macos_xattr_is_published(self, action) -> None:
        """Test the flag attribute is reported as present and empty."""
        result = action._process_xattrs(self.MACOS_LX, xattr_type="macos")

        assert result["xattrs"]["com"]["o0o"]["emptyflag"] == {
            "encoding": "utf-8",
            "value": "",
        }

    def test_a_macos_xattr_with_a_value_still_carries_it(self, action) -> None:
        """Test publishing the empty one leaves the other alone."""
        result = action._process_xattrs(self.MACOS_LX, xattr_type="macos")

        assert result["xattrs"]["com"]["o0o"]["hasvalue"] == {
            "encoding": "utf-8",
            "value": "hello",
        }

    def test_a_zero_length_linux_xattr_is_published(self, action) -> None:
        """Test getfattr's empty value publishes in the same form, so
        an attribute reads alike on either platform."""
        source = '# file: f\nuser.emptyflag=""\nuser.hasvalue="hello"\n'

        result = action._process_xattrs(source, xattr_type="linux")

        assert result["xattrs"]["user"]["emptyflag"] == {
            "encoding": "utf-8",
            "value": "",
        }
        assert result["xattrs"]["user"]["hasvalue"] == {
            "encoding": "utf-8",
            "value": "hello",
        }

    def test_no_xattr_output_publishes_no_xattrs(self, action) -> None:
        """Test nothing to parse still means no attributes, which is a
        different answer than an attribute with no value."""
        assert action._process_xattrs("", xattr_type="macos") == {"xattrs": {}}
        assert action._process_xattrs(None, xattr_type="linux") == {
            "xattrs": {}
        }


class TestProbeIsText:
    """Tests for _probe_is_text."""

    @pytest.mark.parametrize(
        "content_bytes",
        [
            b"",  # nothing to look at is not a reason to call it binary
            b"\n",  # one byte, and file has no magic that short
            b"a",
            b"abc\n",
            b"keeps   \n",
            b"h\xc3\xa9llo\n",  # valid UTF-8
            b"tab\there\r\n",
        ],
    )
    def test_text_bytes_overturn_the_verdict(
        self, action, content_bytes
    ) -> None:
        """Test bytes that read as text are text."""
        assert action._probe_is_text(content_bytes) is True

    @pytest.mark.parametrize(
        "content_bytes",
        [
            b"\x00\x00\x00",  # short, but genuinely not text
            b"\x00",
            b"\x7f\x7f",
            b"\xff\xfe\x00\x00",  # not valid UTF-8 at all
            b"text then \x01 a control byte",
        ],
    )
    def test_binary_bytes_keep_the_verdict(
        self, action, content_bytes
    ) -> None:
        """Test bytes that are not text keep the verdict they got."""
        assert action._probe_is_text(content_bytes) is False


class TestAddContentWithEncoding:
    """Tests for _add_content_with_encoding."""

    @pytest.mark.parametrize(
        "raw,expected_lines",
        [
            ("", []),
            ("\n", [""]),
            ("a", ["a"]),
        ],
    )
    def test_short_text_is_not_binary(
        self, action, raw, expected_lines
    ) -> None:
        """Test a file too short for file's magic still reads as text.

        file reports anything it has no magic for as binary, which
        takes in every one-byte file and the empty file. Believing it
        handed back base64 for no reason but the file's length, and
        refused to split it into lines at all.
        """
        attributes = {}

        action._add_content_with_encoding(
            attributes,
            raw,
            "binary",
            "/tmp/f",
            {"content": True, "lines": True},
        )

        assert attributes == {
            "encoding": "utf-8",
            "content": raw,
            "lines": expected_lines,
        }

    def test_short_binary_keeps_its_verdict(self, action) -> None:
        """Test a short file that is not text is still base64."""
        attributes = {}

        action._add_content_with_encoding(
            attributes,
            "\x00\x00\x00",
            "binary",
            "/tmp/f",
            {"content": True},
        )

        assert attributes == {"encoding": "base64", "content": "AAAA"}

    def test_forced_binary_encoding_is_not_second_guessed(
        self, action
    ) -> None:
        """Test a caller who asked for base64 is given base64."""
        attributes = {}

        action._add_content_with_encoding(
            attributes,
            "abc\n",
            "base64",
            "/tmp/f",
            {"content": True},
            forced=True,
        )

        assert attributes == {"encoding": "base64", "content": "YWJjCg=="}

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

    # binary and unknown only ever arrive from the probes, and the
    # probes are overruled by text bytes now, so those two rows carry
    # bytes that are genuinely not text
    @pytest.mark.parametrize(
        "raw,encoding,expected",
        [
            ("hi", "hex", "hex"),
            ("hi", "base64", "base64"),
            ("\x00\x00", "binary", "base64"),
            ("\x00\x00", "unknown", "base64"),
        ],
    )
    def test_nontext_without_content_records_encoding_only(
        self, action, raw, encoding, expected
    ) -> None:
        """Test non-text encodings honor the content flag like text."""
        attributes = {}

        action._add_content_with_encoding(
            attributes, raw, encoding, "/tmp/f", {}
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

    @pytest.mark.parametrize(
        "raw,expected_lines",
        [
            # A terminated file keeps its terminator
            ("abc\n", ["abc"]),
            # An unterminated one is not given one
            ("abc", ["abc"]),
            # Trailing spaces on the last line are content
            ("abc   \n", ["abc   "]),
            ("abc   ", ["abc   "]),
            # A file holding one newline is not an empty file
            ("\n", [""]),
            ("", []),
            # A blank line at the end survives as the newline pair
            # that makes it
            ("abc\n\n", ["abc", ""]),
        ],
    )
    def test_trailing_bytes_are_content(
        self, action, raw, expected_lines
    ) -> None:
        """Test the file's real trailing bytes reach content untouched.

        The cat these bytes arrive from opts out of run's strip, so
        what this seam is handed is what the file holds. Lines are
        unaffected: splitlines drops the terminator either way.
        """
        attributes = {}

        action._add_content_with_encoding(
            attributes,
            raw,
            "utf-8",
            "/tmp/f",
            {"content": True, "lines": True},
        )

        assert attributes["content"] == raw
        assert attributes["lines"] == expected_lines

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
        "raw,encoding,expected",
        [
            ("hi", "base64", "aGk="),
            ("hi", "Base64", "aGk="),
            ("\x00\x00", "binary", "AAA="),
            ("\x00\x00", "unknown", "AAA="),
            ("\x00\x00", "UNKNOWN", "AAA="),
        ],
    )
    def test_binary_encodings_emit_base64(
        self, action, raw, encoding, expected
    ) -> None:
        """Test binary style encodings all report base64 content."""
        attributes = {}

        action._add_content_with_encoding(
            attributes, raw, encoding, "/tmp/f", {"content": True}
        )

        assert attributes == {"encoding": "base64", "content": expected}

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
        "raw,encoding",
        [
            ("hi", "hex"),
            ("hi", "base64"),
            ("\x00\x00", "binary"),
            ("\x00\x00", "unknown"),
        ],
    )
    def test_lines_with_binary_encoding_raises(
        self, action, raw, encoding
    ) -> None:
        """Test asking for lines with a binary encoding is rejected."""
        attributes = {}

        with pytest.raises(ValueError, match="Cannot split binary content"):
            action._add_content_with_encoding(
                attributes, raw, encoding, "/tmp/f", {"lines": True}
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
