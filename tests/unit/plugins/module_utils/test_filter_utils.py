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


def test_process_registered_result_with_base64_content() -> None:
    """Content payloads attempt plain parse then fall back to base64 decode."""

    text = "Filesystem     1024-blocks"
    encoded = base64.b64encode(text.encode()).decode()

    attempts = []

    def parser(value: str) -> str:
        attempts.append(value)
        if value != text:
            raise ValueError("need decoded text")
        return value

    payload = {"content": encoded, "encoding": "base64"}
    result = filter_utils.process_registered_result(payload, parser)

    assert result == text
    assert attempts == [encoded, text]


def test_process_registered_result_missing_keys() -> None:
    """Dicts without stdout/content raise a ValueError."""

    with pytest.raises(ValueError, match="stdout"):
        filter_utils.process_registered_result({}, lambda value: value)
