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

"""Unit tests for shared filter utilities."""

from __future__ import annotations

import base64
from typing import Any

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils import filter_utils


def test_process_registered_result_with_stdout() -> None:
    """Stdout payloads are passed directly to the parser."""

    seen: Any = None

    def parser(value: str) -> str:
        nonlocal seen
        seen = value
        return value.upper()

    payload = {"stdout": "hello"}
    result = filter_utils.process_registered_result(payload, parser)

    assert result == "HELLO"
    assert seen == "hello"


def test_process_registered_result_honors_declared_base64() -> None:
    """A declared base64 encoding is decoded before any parse."""

    text = "Filesystem     1024-blocks"
    encoded = base64.b64encode(text.encode()).decode()

    attempts = []

    def parser(value: str) -> str:
        attempts.append(value)
        return value

    payload = {"content": encoded, "encoding": "base64"}
    result = filter_utils.process_registered_result(payload, parser)

    assert result == text
    # The encoded text is never offered to the parser: one that
    # accepted it would report fiction
    assert attempts == [text]


def test_process_registered_result_honors_declared_hex() -> None:
    """A declared hex encoding is decoded before any parse."""

    text = "Filesystem     1024-blocks"
    encoded = text.encode().hex()

    attempts = []

    def parser(value: str) -> str:
        attempts.append(value)
        return value

    payload = {"content": encoded, "encoding": "hex"}
    result = filter_utils.process_registered_result(payload, parser)

    assert result == text
    assert attempts == [text]


def test_process_registered_result_guesses_undeclared_base64() -> None:
    """Without a declaration, try plain parse then base64 decode."""

    text = "Filesystem     1024-blocks"
    encoded = base64.b64encode(text.encode()).decode()

    attempts = []

    def parser(value: str) -> str:
        attempts.append(value)
        if value != text:
            raise ValueError("need decoded text")
        return value

    payload = {"content": encoded}
    result = filter_utils.process_registered_result(payload, parser)

    assert result == text
    assert attempts == [encoded, text]


def test_process_registered_result_missing_keys() -> None:
    """Dicts without stdout/content raise a ValueError."""

    with pytest.raises(ValueError, match="stdout"):
        filter_utils.process_registered_result({}, lambda value: value)


TEXT = "/dev/sda1 / ext4 defaults 0 1\n"


@pytest.mark.parametrize(
    "encoding,content",
    [
        ("base64", base64.b64encode(TEXT.encode()).decode()),
        ("hex", TEXT.encode().hex()),
        # A declaration names the same encoding whatever its case
        ("HEX", TEXT.encode().hex()),
    ],
)
def test_declared_encodings_are_decoded(encoding, content) -> None:
    """An encoded representation is decoded to the file's text."""

    assert filter_utils.decode_declared_content(content, encoding) == TEXT


@pytest.mark.parametrize("encoding", [None, "", "utf-8", "iso-8859-1"])
def test_undecoded_declarations_report_nothing(encoding) -> None:
    """A text encoding or no declaration at all decodes nothing."""

    assert filter_utils.decode_declared_content(TEXT, encoding) is None


@pytest.mark.parametrize("encoding", ["base64", "hex"])
def test_content_that_belies_its_declaration_raises(encoding) -> None:
    """A declaration is authoritative, so a payload that fails it
    fails the filter rather than parsing as text."""

    with pytest.raises(ValueError):
        filter_utils.decode_declared_content("not encoded at all", encoding)


@pytest.mark.parametrize(
    "source,expected",
    [
        # Device paths
        ("/dev/sda1", {"path": "/dev/sda1"}),
        ("/dev/disk3s1s1", {"path": "/dev/disk3s1s1"}),
        ("/dev/mapper/vg-lv", {"path": "/dev/mapper/vg-lv"}),
        # UUID formats
        ("UUID=abc-123-def", {"uuid": "abc-123-def", "partition": False}),
        ("PARTUUID=xyz-456", {"uuid": "xyz-456", "partition": True}),
        ("uuid=lowercase", {"uuid": "lowercase", "partition": False}),
        # Label formats
        ("LABEL=root", {"label": "root", "partition": False}),
        ("PARTLABEL=system", {"label": "system", "partition": True}),
        ("label=MyDisk", {"label": "MyDisk", "partition": False}),
        # Network paths (NFS)
        ("server:/export", {"address": "server:/export"}),
        (
            "server.domain:/path/to/share",
            {"address": "server.domain:/path/to/share"},
        ),
        ("192.168.1.1:/nfs", {"address": "192.168.1.1:/nfs"}),
        # Network paths (SMB/CIFS)
        ("//server/share", {"address": "//server/share"}),
        ("//192.168.1.1/share", {"address": "//192.168.1.1/share"}),
        # Automounter maps
        ("map auto_home", {"map": "auto_home"}),
        ("map -hosts", {"map": "-hosts"}),
        # Special filesystems
        ("proc", {"name": "proc"}),
        ("sysfs", {"name": "sysfs"}),
        ("tmpfs", {"name": "tmpfs"}),
        ("devpts", {"name": "devpts"}),
        # Bind mounts and other paths
        ("/home", {"path": "/home"}),
        ("/mnt/data", {"path": "/mnt/data"}),
        ("/", {"path": "/"}),
        # Special cases that return None
        ("none", None),
        ("-", None),
    ],
)
def test_normalize_source(source: str, expected: dict) -> None:
    """Test source normalization for various formats."""
    result = filter_utils.normalize_source(source)
    assert result == expected


def test_normalize_source_uuid_case_insensitive() -> None:
    """Test that UUID matching is case-insensitive."""
    assert filter_utils.normalize_source("UUID=test") == {
        "uuid": "test",
        "partition": False,
    }
    assert filter_utils.normalize_source("uuid=test") == {
        "uuid": "test",
        "partition": False,
    }
    assert filter_utils.normalize_source("Uuid=test") == {
        "uuid": "test",
        "partition": False,
    }
    assert filter_utils.normalize_source("PARTUUID=test") == {
        "uuid": "test",
        "partition": True,
    }
    assert filter_utils.normalize_source("partuuid=test") == {
        "uuid": "test",
        "partition": True,
    }


def test_normalize_source_none_cases() -> None:
    """Test that 'none' and '-' return None."""
    assert filter_utils.normalize_source("none") is None
    assert filter_utils.normalize_source("-") is None
    # But other strings starting with these should not
    assert filter_utils.normalize_source("none-device") == {
        "name": "none-device"
    }
    assert filter_utils.normalize_source("-device") == {"name": "-device"}


def test_normalize_source_label_case_insensitive() -> None:
    """Test that LABEL matching is case-insensitive."""
    assert filter_utils.normalize_source("LABEL=test") == {
        "label": "test",
        "partition": False,
    }
    assert filter_utils.normalize_source("label=test") == {
        "label": "test",
        "partition": False,
    }
    assert filter_utils.normalize_source("Label=test") == {
        "label": "test",
        "partition": False,
    }
    assert filter_utils.normalize_source("PARTLABEL=test") == {
        "label": "test",
        "partition": True,
    }
    assert filter_utils.normalize_source("partlabel=test") == {
        "label": "test",
        "partition": True,
    }
