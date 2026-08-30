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

"""Unit tests for group module_utils helpers."""

from __future__ import annotations

from base64 import b64encode
from typing import Any

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils import group_info

GROUP_TEXT = "staff:*:20:root\n"

SAMPLE_GROUPS = [
    {"group_name": "staff", "gid": 20, "members": ["root"]},
    {"group_name": "access_bpf", "gid": 101, "members": []},
    {"group_name": None, "gid": 61, "members": []},
]


@pytest.mark.parametrize("config", [SAMPLE_GROUPS, {"stdout": ""}])
def test_group_info_key_id(
    config: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Numeric keyed result mirrors id filter group structure."""

    if isinstance(config, dict):
        monkeypatch.setattr(
            "ansible_collections.o0_o.posix.plugins.module_utils.group_utils.jc_parse",  # noqa: E501
            lambda parser, data, **kwargs: SAMPLE_GROUPS,
        )

    result = group_info(config, key="id")

    assert result == {
        "20": {"name": "staff", "members": ["root"]},
        "101": {"name": "access_bpf", "members": []},
        "61": {"name": None, "members": []},
    }


def test_group_info_key_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Name keyed result maps to id with fallback for unnamed groups."""

    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.module_utils.group_utils.jc_parse",  # noqa: E501
        lambda parser, data, **kwargs: SAMPLE_GROUPS,
    )

    result = group_info("/etc/group contents", key="name")

    assert result["staff"] == {"id": 20, "members": ["root"]}
    assert result["access_bpf"] == {"id": 101, "members": []}
    assert result["61"] == {"id": 61, "members": []}


def test_group_info_decodes_declared_base64() -> None:
    """Content a read result declares base64 is decoded, not parsed."""

    read_result = {
        "content": b64encode(GROUP_TEXT.encode()).decode(),
        "encoding": "base64",
    }

    assert group_info(read_result, key="id") == {
        "20": {"name": "staff", "members": ["root"]}
    }


def test_group_info_decodes_declared_hex() -> None:
    """Content a read result declares hex is decoded, not parsed."""

    read_result = {
        "content": GROUP_TEXT.encode().hex(),
        "encoding": "hex",
    }

    assert group_info(read_result, key="id") == {
        "20": {"name": "staff", "members": ["root"]}
    }


def test_group_info_invalid_key() -> None:
    """Invalid key values raise ValueError."""

    with pytest.raises(ValueError, match="Unsupported key"):
        group_info(SAMPLE_GROUPS, key="invalid")


def test_group_info_handles_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty input returns empty mapping."""

    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.module_utils.group_utils.jc_parse",  # noqa: E501
        lambda parser, data, **kwargs: [],
    )

    assert group_info({"stdout": ""}) == {}


def test_group_info_normalizes_string_members(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """String-based member fields are split and trimmed."""

    sample_groups = [
        {"group_name": "docker", "gid": 202, "members": "root,o0-o"},
        {"group_name": "mock", "gid": 203, "members": None, "users": ""},
        {
            "group_name": "build",
            "gid": 204,
            "members": None,
            "users": "ci,build",
        },
    ]

    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.module_utils.group_utils.jc_parse",  # noqa: E501
        lambda parser, data, **kwargs: sample_groups,
    )

    result = group_info("/etc/group", key="id")

    assert result["202"]["members"] == ["root", "o0-o"]
    assert result["203"]["members"] == []
    assert result["204"]["members"] == ["ci", "build"]


# What ``getent group`` prints on each platform, captured off running
# hosts. The BSDs drop the empty members field along with its
# delimiter; every flat file, theirs included, keeps both.
BSD_GETENT_GROUP = "wheel:*:0:root,ci\ndaemon:*:1:daemon\nbin:*:7\n"
LINUX_GETENT_GROUP = "root:x:0:\ndaemon:x:1:daemon\nbin:x:2:\n"


def test_group_info_reads_a_line_with_no_members_field() -> None:
    """A BSD getent's short line is a group, not a malformed line.

    FreeBSD and OpenBSD print ``bin:*:7`` for a group nobody is a
    secondary member of. The parser used to raise on it, which reads
    to a caller as a host whose getent could not be believed rather
    than as the BSD it is.
    """
    result = group_info(BSD_GETENT_GROUP, key="id")

    assert result["7"] == {"name": "bin", "members": []}
    assert result["0"]["members"] == ["root", "ci"]
    assert result["1"]["members"] == ["daemon"]


def test_group_info_reads_both_spellings_the_same_way() -> None:
    """The delimiter a producer left off does not reach the fact."""
    padded = group_info(LINUX_GETENT_GROUP, key="id")
    short = group_info(BSD_GETENT_GROUP, key="id")

    assert padded["1"]["members"] == short["1"]["members"]
    assert padded["0"]["members"] == []
    assert short["7"]["members"] == []


def test_group_info_restores_the_field_in_a_registered_result() -> None:
    """A short line reads the same from text and from a result."""
    from_text = group_info(BSD_GETENT_GROUP, key="id")

    assert group_info({"stdout": BSD_GETENT_GROUP}, key="id") == from_text
    assert group_info({"content": BSD_GETENT_GROUP}, key="id") == from_text


def test_group_info_restores_the_field_after_decoding() -> None:
    """The rewrite runs on the file, never on the blob carrying it.

    A read result declares its encoding, and content is decoded before
    a parser sees it. Restoring the field before that would rewrite
    base64 rather than a group line.
    """
    encoded = b64encode(BSD_GETENT_GROUP.encode()).decode()

    assert group_info(
        {"content": encoded, "encoding": "base64"}, key="id"
    ) == group_info(BSD_GETENT_GROUP, key="id")


def test_group_info_leaves_comments_and_blank_lines_alone() -> None:
    """Padding is for group lines, not for everything short."""
    result = group_info("# a comment with one : colon\n\nbin:*:7\n", key="id")

    assert result == {"7": {"name": "bin", "members": []}}
