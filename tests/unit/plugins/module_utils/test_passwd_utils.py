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

"""Unit tests for passwd module_utils helpers."""

from __future__ import annotations

from base64 import b64encode
from typing import Any

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils import passwd_info

PASSWD_TEXT = "root:*:0:0:System Administrator:/var/root:/bin/sh\n"

SAMPLE_PASSWD = [
    {
        "username": "root",
        "uid": 0,
        "gid": 0,
        "comment": "System Administrator",
        "home": "/var/root",
        "shell": "/bin/sh",
    },
    {
        "username": "o0-o",
        "uid": 1000,
        "gid": 20,
        "comment": "o0-o",
        "home": "/Users/o0-o",
        "shell": "/bin/zsh",
    },
]


@pytest.mark.parametrize("config", [SAMPLE_PASSWD, {"stdout": ""}])
def test_passwd_info_key_id(
    config: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Numeric keyed result matches jc structure."""

    if isinstance(config, dict):
        monkeypatch.setattr(
            "ansible_collections.o0_o.posix.plugins.module_utils.passwd_utils.jc_parse",  # noqa: E501
            lambda parser, data: SAMPLE_PASSWD,
        )

    result = passwd_info(config, key="id")

    assert result["1000"]["name"] == "o0-o"
    assert result["1000"]["gid"] == 20
    assert result["1000"]["home"] == "/Users/o0-o"
    assert result["1000"]["gecos"] == "o0-o"
    assert result["0"]["shell"] == "/bin/sh"


def test_passwd_info_key_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Name keyed result maps to uid with metadata."""

    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.module_utils.passwd_utils.jc_parse",  # noqa: E501
        lambda parser, data: SAMPLE_PASSWD,
    )

    result = passwd_info("/etc/passwd", key="name")

    assert result["o0-o"]["id"] == 1000
    assert result["o0-o"]["gid"] == 20
    assert result["o0-o"]["shell"] == "/bin/zsh"
    assert result["o0-o"]["gecos"] == "o0-o"


def test_passwd_info_decodes_declared_base64() -> None:
    """Content a read result declares base64 is decoded, not parsed."""

    read_result = {
        "content": b64encode(PASSWD_TEXT.encode()).decode(),
        "encoding": "base64",
    }

    assert passwd_info(read_result, key="name") == {
        "root": {
            "gid": 0,
            "gecos": "System Administrator",
            "home": "/var/root",
            "shell": "/bin/sh",
            "id": 0,
        }
    }


def test_passwd_info_decodes_declared_hex() -> None:
    """Content a read result declares hex is decoded, not parsed."""

    read_result = {
        "content": PASSWD_TEXT.encode().hex(),
        "encoding": "hex",
    }

    assert passwd_info(read_result, key="name") == {
        "root": {
            "gid": 0,
            "gecos": "System Administrator",
            "home": "/var/root",
            "shell": "/bin/sh",
            "id": 0,
        }
    }


def test_passwd_info_invalid_key() -> None:
    """Invalid key values raise ValueError."""

    with pytest.raises(ValueError, match="Unsupported key"):
        passwd_info(SAMPLE_PASSWD, key="invalid")


def test_passwd_info_handles_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty input returns empty mapping."""

    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.module_utils.passwd_utils.jc_parse",  # noqa: E501
        lambda parser, data: [],
    )

    assert passwd_info({"stdout": ""}) == {}
