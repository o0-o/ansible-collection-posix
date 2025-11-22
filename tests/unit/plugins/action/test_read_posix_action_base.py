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

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_get_stat_commands_stage1_basic(read_base):
    """Test stage 1 command generation with basic parameters."""
    commands = read_base._get_stat_commands_stage1(
        path="/tmp/testfile", get_mime=True
    )

    # Verify command structure
    assert isinstance(commands, list)
    assert all(isinstance(cmd, tuple) and len(cmd) == 2 for cmd in commands)

    # Extract tags
    tags = [tag for tag, cmd in commands]

    # Verify required commands
    assert "stat_main" in tags
    assert "readlink" in tags
    assert "readlink_f" in tags
    assert "test_x" in tags
    assert "mime" in tags  # Because get_mime=True


def test_get_stat_commands_stage1_no_mime(read_base):
    """Test stage 1 command generation without MIME detection."""
    commands = read_base._get_stat_commands_stage1(
        path="/tmp/testfile", get_mime=False
    )

    tags = [tag for tag, cmd in commands]
    assert "mime" not in tags


def test_get_stat_commands_stage2_basic(read_base):
    """Test stage 2 command generation with basic parameters."""
    commands = read_base._get_stat_commands_stage2(
        path="/tmp/testfile",
        username="testuser",
        groupname="testgroup",
        is_symlink=False,
        follow=False,
        file_type_char="-",
        is_regular_file=True,
        get_checksum=False,
        checksum_algorithm="sha1",
        get_attributes=False,
    )

    tags = [tag for tag, cmd in commands]

    # Basic commands always present
    assert "uid" in tags
    assert "gid" in tags

    # No checksum or attributes
    assert "checksum_gnu" not in tags
    assert "checksum_bsd_shasum" not in tags
    assert "attrs_lsattr" not in tags


def test_get_stat_commands_stage2_with_checksum(read_base):
    """Test stage 2 includes checksum commands when requested."""
    commands = read_base._get_stat_commands_stage2(
        path="/tmp/testfile",
        username="user",
        groupname="group",
        is_symlink=False,
        follow=False,
        file_type_char="-",
        is_regular_file=True,
        get_checksum=True,
        checksum_algorithm="sha256",
        get_attributes=False,
    )

    tags = [tag for tag, cmd in commands]

    # Should include checksum commands
    assert (
        "checksum_gnu" in tags
        or "checksum_bsd_shasum" in tags
        or "checksum_bsd_md5" in tags
    )


def test_get_stat_commands_stage2_with_attributes(read_base):
    """Test stage 2 includes attribute commands when requested."""
    commands = read_base._get_stat_commands_stage2(
        path="/tmp/testfile",
        username="user",
        groupname="group",
        is_symlink=False,
        follow=False,
        file_type_char="-",
        is_regular_file=True,
        get_checksum=False,
        checksum_algorithm="sha1",
        get_attributes=True,
    )

    tags = [tag for tag, cmd in commands]

    # Should include attribute commands
    assert "attrs_lsattr" in tags or "attrs_ls" in tags


def test_get_stat_commands_stage2_symlink_follow(read_base):
    """Test stage 2 includes stat -L for symlinks with follow=True."""
    commands = read_base._get_stat_commands_stage2(
        path="/tmp/symlink",
        username="user",
        groupname="group",
        is_symlink=True,
        follow=True,
        file_type_char="l",
        is_regular_file=False,
        get_checksum=False,
        checksum_algorithm="sha1",
        get_attributes=False,
    )

    tags = [tag for tag, cmd in commands]
    assert "stat_follow" in tags


def test_get_stat_commands_stage2_device_file(read_base):
    """Test stage 2 includes device type command for block/char devices."""
    for file_type in ("b", "c"):
        commands = read_base._get_stat_commands_stage2(
            path="/dev/sda",
            username="root",
            groupname="root",
            is_symlink=False,
            follow=False,
            file_type_char=file_type,
            is_regular_file=False,
            get_checksum=False,
            checksum_algorithm="sha1",
            get_attributes=False,
        )

        tags = [tag for tag, cmd in commands]
        assert "device_type" in tags


def test_parse_checksum_from_results_gnu(read_base):
    """Test checksum parsing from GNU coreutils output."""
    tagged_results = {
        "checksum_gnu": {
            "rc": 0,
            "stdout": "abc123def456  /tmp/testfile\n",
        }
    }

    checksum = read_base._parse_checksum_from_results(tagged_results, "sha256")
    assert checksum == "abc123def456"


def test_parse_checksum_from_results_bsd_shasum(read_base):
    """Test checksum parsing from BSD shasum output."""
    tagged_results = {
        "checksum_gnu": {"rc": 1, "stdout": ""},
        "checksum_bsd_shasum": {
            "rc": 0,
            "stdout": "xyz789abc123  /tmp/testfile\n",
        },
    }

    checksum = read_base._parse_checksum_from_results(tagged_results, "sha256")
    assert checksum == "xyz789abc123"


def test_parse_checksum_from_results_bsd_md5(read_base):
    """Test checksum parsing from BSD md5 output with -q flag."""
    tagged_results = {
        "checksum_gnu": {"rc": 1, "stdout": ""},
        "checksum_bsd_shasum": {"rc": 1, "stdout": ""},
        "checksum_bsd_md5": {
            "rc": 0,
            "stdout": "abc123def456\n",  # md5 -q outputs just the hash
        },
    }

    checksum = read_base._parse_checksum_from_results(tagged_results, "md5")
    assert checksum == "abc123def456"


def test_parse_checksum_from_results_none_available(read_base):
    """Test checksum parsing returns None when no commands succeed."""
    tagged_results = {
        "checksum_gnu": {"rc": 1, "stdout": ""},
        "checksum_bsd_shasum": {"rc": 1, "stdout": ""},
        "checksum_bsd_md5": {"rc": 1, "stdout": ""},
    }

    checksum = read_base._parse_checksum_from_results(tagged_results, "sha256")
    assert checksum is None


def test_parse_attributes_from_results_lsattr(read_base):
    """Test attributes parsing from lsattr output."""
    tagged_results = {
        "attrs_lsattr": {
            "rc": 0,
            "stdout": "--------------e------- /tmp/testfile\n",
        }
    }

    attrs = read_base._parse_attributes_from_results(tagged_results)
    assert attrs == "--------------e-------"


def test_parse_attributes_from_results_ls_bsd(read_base):
    """Test attributes parsing from BSD ls -ldO output."""
    tagged_results = {
        "attrs_lsattr": {"rc": 1, "stdout": ""},
        "attrs_ls": {
            "rc": 0,
            "stdout": "-rw-r--r--  1 user  group  hidden,compressed 1024 Jan 1 00:00 /tmp/testfile\n",  # noqa: E501
        },
    }

    attrs = read_base._parse_attributes_from_results(tagged_results)
    # Should extract the flags part from ls output
    assert attrs is not None
    assert "hidden,compressed" in attrs or attrs == "hidden,compressed"


def test_parse_attributes_from_results_none_available(read_base):
    """Test attributes parsing returns None when no commands succeed."""
    tagged_results = {
        "attrs_lsattr": {"rc": 1, "stdout": ""},
        "attrs_ls": {"rc": 1, "stdout": ""},
    }

    attrs = read_base._parse_attributes_from_results(tagged_results)
    assert attrs is None


@pytest.mark.parametrize(
    "algorithm,gnu_cmd",
    [
        ("md5", "md5sum"),
        ("sha1", "sha1sum"),
        ("sha224", "sha224sum"),
        ("sha256", "sha256sum"),
        ("sha384", "sha384sum"),
        ("sha512", "sha512sum"),
    ],
)
def test_get_stat_commands_stage2_checksum_algorithms(
    read_base, algorithm, gnu_cmd
):
    """Test stage 2 generates correct checksum commands for each algorithm."""
    commands = read_base._get_stat_commands_stage2(
        path="/tmp/testfile",
        username="user",
        groupname="group",
        is_symlink=False,
        follow=False,
        file_type_char="-",
        is_regular_file=True,
        get_checksum=True,
        checksum_algorithm=algorithm,
        get_attributes=False,
    )

    # Find the GNU checksum command
    gnu_command = None
    for tag, cmd in commands:
        if tag == "checksum_gnu":
            gnu_command = cmd
            break

    # Verify the correct command is used
    if gnu_command:
        assert gnu_cmd in gnu_command[0] or gnu_command[0] == gnu_cmd


def test_process_stat_stage1_basic(read_base, monkeypatch):
    """Test stage 1 processing with valid jc output."""

    # Mock jc_parse
    def mock_jc_parse(parser, data):
        return [
            {
                "file": "/tmp/testfile",
                "flags": "-rw-r--r--",
                "user": "testuser",
                "group": "testgroup",
                "size": 1024,
                "links": 1,
                "inode": 12345,
                "device_major": 8,
                "device_minor": 1,
                "access_time_epoch": 1700000000,
                "modify_time_epoch": 1700000001,
                "change_time_epoch": 1700000002,
                "blocks": 8,
                "block_size": 4096,
            }
        ]

    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.module_utils.read_posix_action_base.jc_parse",  # noqa: E501
        mock_jc_parse,
    )

    tagged_results = {
        "stat_main": {"rc": 0, "stdout": "stat output"},
        "readlink": {"rc": 1, "stdout": ""},
        "readlink_f": {"rc": 1, "stdout": ""},
        "test_x": {"rc": 1, "stdout": ""},
    }

    partial_stat, stage2_params = read_base._process_stat_stage1(
        tagged_results, "/tmp/testfile", follow=False
    )

    # Verify partial stat
    assert partial_stat["exists"] is True
    assert partial_stat["path"] == "/tmp/testfile"
    assert partial_stat["size"] == 1024

    # Verify stage2_params
    assert stage2_params["username"] == "testuser"
    assert stage2_params["groupname"] == "testgroup"
    assert stage2_params["is_symlink"] is False
    assert stage2_params["file_type_char"] == "-"
    assert stage2_params["is_regular_file"] is True


def test_process_stat_stage1_symlink(read_base, monkeypatch):
    """Test stage 1 processing identifies symlinks correctly."""

    def mock_jc_parse(parser, data):
        return [
            {
                "file": "/tmp/symlink",
                "flags": "lrwxrwxrwx",
                "user": "user",
                "group": "group",
                "size": 10,
                "links": 1,
                "inode": 54321,
                "device_major": 8,
                "device_minor": 1,
                "access_time_epoch": 1700000000,
                "modify_time_epoch": 1700000001,
                "change_time_epoch": 1700000002,
                "blocks": 0,
                "block_size": 4096,
            }
        ]

    monkeypatch.setattr(
        "ansible_collections.o0_o.posix.plugins.module_utils.read_posix_action_base.jc_parse",  # noqa: E501
        mock_jc_parse,
    )

    tagged_results = {
        "stat_main": {"rc": 0, "stdout": "stat output"},
        "readlink": {"rc": 0, "stdout": "/tmp/target\n"},
        "readlink_f": {"rc": 0, "stdout": "/tmp/target\n"},
        "test_x": {"rc": 1, "stdout": ""},
    }

    partial_stat, stage2_params = read_base._process_stat_stage1(
        tagged_results, "/tmp/symlink", follow=False
    )

    # Verify symlink detection
    assert stage2_params["is_symlink"] is True
    assert stage2_params["file_type_char"] == "l"
    assert stage2_params["is_regular_file"] is False


def test_process_stat_stage2_basic(read_base, monkeypatch):
    """Test stage 2 processing merges results correctly."""
    # Mock helper methods
    read_base._parse_checksum_from_results = MagicMock(return_value="abc123")
    read_base._parse_attributes_from_results = MagicMock(
        return_value="--------------e-------"
    )
    read_base._extract_attr_flags = MagicMock(return_value="e")
    read_base._normalize_flags = MagicMock(return_value=["extents"])
    read_base._stat_device_type = MagicMock(return_value=0)
    read_base._stat_mode_from_flags = MagicMock(return_value="0644")
    read_base._stat_permission_booleans = MagicMock(
        return_value={"rusr": True, "wusr": True, "xusr": False}
    )

    partial_stat = {
        "exists": True,
        "path": "/tmp/testfile",
        "size": 1024,
        "pw_name": "testuser",
        "gr_name": "testgroup",
    }

    stage2_params = {
        "username": "testuser",
        "groupname": "testgroup",
        "is_symlink": False,
        "follow": False,
        "file_type_char": "-",
        "is_regular_file": True,
        "jc_data": {"flags": "-rw-r--r--"},
        "flags": "-rw-r--r--",
        "is_bsd": False,
    }

    tagged_results = {
        "uid": {"rc": 0, "stdout": "1000\n"},
        "gid": {"rc": 0, "stdout": "1000\n"},
        "checksum_gnu": {"rc": 0, "stdout": "abc123  /tmp/testfile\n"},
        "attrs_lsattr": {"rc": 0, "stdout": "--------------e-------\n"},
    }

    stage1_tagged_results = {
        "test_x": {"rc": 1, "stdout": ""},
        "mime": {"rc": 0, "stdout": "text/plain; charset=utf-8\n"},
    }

    stat_result = read_base._process_stat_stage2(
        tagged_results=tagged_results,
        stage1_tagged_results=stage1_tagged_results,
        partial_stat=partial_stat,
        stage2_params=stage2_params,
        path="/tmp/testfile",
        get_checksum=True,
        checksum_algorithm="sha256",
        get_mime=True,
        get_attributes=True,
        task_vars={},
    )

    # Verify merged result
    assert stat_result["uid"] == 1000
    assert stat_result["gid"] == 1000
    assert stat_result["checksum"] == "abc123"
    assert stat_result["attr_flags"] == "e"
    assert stat_result["attributes"] == ["extents"]
    assert stat_result["mimetype"] == "text/plain"
    assert stat_result["charset"] == "utf-8"
