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

"""Unit tests for stat module_utils helpers."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils import stat_utils


LINUX_ENTRY: Dict[str, Any] = {
    "file": "/tmp/example",
    "size": 4096,
    "blocks": 8,
    "io_blocks": 4096,
    "type": "regular file",
    "device": "802h/2050d",
    "inode": 131099,
    "links": 2,
    "access": "0755",
    "flags": "-rwxr-xr-x",
    "uid": 0,
    "user": "root",
    "gid": 0,
    "group": "root",
    "access_time_epoch": 1,
    "modify_time_epoch": 2,
    "change_time_epoch": 3,
    "birth_time_epoch": None,
}


BSD_ENTRY: Dict[str, Any] = {
    "file": "/tmp/macos",
    "unix_device": "16777220",
    "inode": "45479536",
    "flags": "-rw-r--r--",
    "links": "1",
    "user": "alice",
    "group": "staff",
    "rdev": "0",
    "size": "42",
    "access_time_epoch": 11,
    "modify_time_epoch": 22,
    "change_time_epoch": 33,
    "birth_time_epoch": 44,
    "block_size": "4096",
    "blocks": "8",
    "unix_flags": "0",
}


@pytest.fixture
def restore_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure pwd/grp helpers are restored after tests."""

    monkeypatch.setattr(stat_utils, "jc_parse", lambda parser, data: [])


def test_stat_normalizes_linux_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Linux style jc data is converted to ansible stat structure."""

    monkeypatch.setattr(
        stat_utils,
        "jc_parse",
        lambda parser, data: [LINUX_ENTRY],
    )

    result = stat_utils.stat("stat output")

    assert result["exists"] is True
    assert result["path"] == "/tmp/example"
    assert result["isreg"] is True
    assert result["isdir"] is False
    assert result["mode"] == "0755"
    assert result["uid"] == 0
    assert result["gid"] == 0
    assert result["pw_name"] == "root"
    assert result["gr_name"] == "root"
    assert result["nlink"] == 2
    assert result["inode"] == 131099
    assert result["dev"] == 2050
    assert result["size"] == 4096
    assert result["atime"] == 1
    assert result["mtime"] == 2
    assert result["ctime"] == 3
    assert result["atime_iso8601"].endswith("Z")
    assert result["xattrs"] == []
    assert result["selinux_label"] is None


def test_stat_normalizes_bsd_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """BSD/macOS output lacks uid/gid so they are resolved via pwd/grp."""

    monkeypatch.setattr(
        stat_utils,
        "jc_parse",
        lambda parser, data: [BSD_ENTRY],
    )

    result = stat_utils.stat("stat output")

    assert result["exists"] is True
    assert result["mode"] == "0644"
    assert result["uid"] is None
    assert result["gid"] is None
    assert result["pw_name"] == "alice"
    assert result["gr_name"] == "staff"
    assert result["isreg"] is True
    assert result["nlink"] == 1
    assert result["block_size"] == 4096
    assert result["blocks"] == 8
    assert result["btime"] == 44


def test_stat_handles_empty_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty jc output reports the path as missing."""

    monkeypatch.setattr(stat_utils, "jc_parse", lambda parser, data: [])

    result = stat_utils.stat("stat output")
    assert result == {"exists": False}


def test_stat_honors_nonzero_rc(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-zero rc inputs short-circuit before invoking jc_parse."""

    called = False

    def fake_parse(parser: str, data: Any) -> Any:
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(stat_utils, "jc_parse", fake_parse)

    result = stat_utils.stat({"rc": 1, "stdout": ""})

    assert result == {"exists": False}
    assert called is False
