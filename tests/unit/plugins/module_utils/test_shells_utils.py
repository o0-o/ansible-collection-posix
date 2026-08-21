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

"""Tests for shells_utils helpers."""

from __future__ import annotations

from base64 import b64encode
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("pyparsing")

MODULE_PATH = (
    Path(__file__).parents[4] / "plugins" / "module_utils" / "shells_utils.py"
)

spec = importlib.util.spec_from_file_location("shells_utils", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

parse_shells = module.parse_shells


def test_parse_shells_from_slurp() -> None:
    """Decode base64 slurp result and strip comments."""

    content = """
# Comment line
/bin/bash  # trailing comment
/bin/zsh
""".strip()
    payload = {
        "content": b64encode(content.encode()).decode(),
        "encoding": "base64",
    }

    result = parse_shells(payload)

    assert result == ["/bin/bash", "/bin/zsh"]


def test_parse_shells_from_declared_hex() -> None:
    """Decode a read result that declares hex and strip comments."""

    content = """
# Comment line
/bin/bash  # trailing comment
/bin/zsh
""".strip()
    payload = {"content": content.encode().hex(), "encoding": "hex"}

    result = parse_shells(payload)

    assert result == ["/bin/bash", "/bin/zsh"]


def test_parse_shells_leaves_undeclared_content_alone() -> None:
    """Text content is not decoded, however base64 it looks."""

    # Every character here is base64 alphabet and the count is a
    # multiple of four, so a decode attempt succeeds and returns junk
    payload = {"content": "/bin/sh\n/bin/bash\n", "encoding": "utf-8"}

    assert parse_shells(payload) == ["/bin/sh", "/bin/bash"]


def test_parse_shells_plain_string() -> None:
    """Handle raw string input."""

    content = "/bin/bash\n# comment\n/bin/fish\n"
    assert parse_shells(content) == ["/bin/bash", "/bin/fish"]


def test_parse_shells_iterable() -> None:
    """Handle iterable of lines."""

    content = ["/bin/bash", "# comment", "/bin/tcsh"]
    assert parse_shells(content) == ["/bin/bash", "/bin/tcsh"]


def test_parse_shells_unknown_returns_empty() -> None:
    """Unsupported types should yield empty list."""

    assert parse_shells(42) == []
