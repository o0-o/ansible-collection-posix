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

from unittest.mock import patch

import pytest
from ansible.errors import AnsibleFilterError


@pytest.fixture
def filter_module():
    """Create a FilterModule instance for testing."""
    from ansible_collections.o0_o.posix.plugins.filter.mount import (
        FilterModule,
    )

    return FilterModule()


def test_mount_parse_linux_output(filter_module):
    """Test parsing Linux mount output."""
    mount_output = """/dev/sda1 on / type ext4 (rw,relatime,errors=remount-ro)
proc on /proc type proc (rw,nosuid,nodev,noexec,relatime)
tmpfs on /dev/shm type tmpfs (rw,nosuid,nodev)"""

    mount_filter = filter_module.filters()["mount"]
    result = mount_filter(mount_output)

    # Verify the result structure matches our expected format
    assert len(result) == 3

    # Check root filesystem
    assert result[0]["source"] == "/dev/sda1"
    assert result[0]["mount"] == "/"
    assert result[0]["type"] == "ext4"
    assert result[0]["options"]["rw"] is True
    assert result[0]["options"]["relatime"] is True
    assert result[0]["options"]["errors"] == "remount-ro"

    # Check proc filesystem
    assert result[1]["source"] == "proc"
    assert result[1]["mount"] == "/proc"
    assert result[1]["type"] == "proc"
    assert result[1]["options"]["rw"] is True
    assert result[1]["options"]["nosuid"] is True

    # Check tmpfs
    assert result[2]["source"] == "tmpfs"
    assert result[2]["mount"] == "/dev/shm"
    assert result[2]["type"] == "tmpfs"


def test_mount_parse_macos_output(filter_module):
    """Test parsing macOS mount output (type in options)."""
    # macOS style output where filesystem type is the first option
    mount_output = "/dev/disk3s1s1 on / (apfs, local, journaled)"

    mount_filter = filter_module.filters()["mount"]
    result = mount_filter(mount_output)

    assert len(result) == 1
    assert result[0]["source"] == "/dev/disk3s1s1"
    assert result[0]["mount"] == "/"
    assert result[0]["type"] == "apfs"  # Extracted from first option
    assert result[0]["options"]["local"] is True
    assert result[0]["options"]["journaled"] is True


def test_mount_parse_with_command_dict(filter_module):
    """Test parsing mount output from command result dict."""
    command_result = {
        "stdout": "/dev/sda1 on / type ext4 (rw,relatime)",
        "stdout_lines": ["/dev/sda1 on / type ext4 (rw,relatime)"],
        "stderr": "",
        "rc": 0,
    }

    mount_filter = filter_module.filters()["mount"]
    result = mount_filter(command_result)

    assert len(result) == 1
    assert result[0]["source"] == "/dev/sda1"
    assert result[0]["mount"] == "/"
    assert result[0]["type"] == "ext4"
    assert result[0]["options"]["rw"] is True


def test_mount_parse_with_slurp_dict(filter_module):
    """Test parsing mount output from slurp result dict (base64)."""
    import base64

    mount_content = "/dev/sda1 on / type ext4 (rw,relatime)"
    encoded = base64.b64encode(mount_content.encode()).decode()

    slurp_result = {
        "content": encoded,
        "source": "/proc/mounts",
        "encoding": "base64",
    }

    mount_filter = filter_module.filters()["mount"]
    result = mount_filter(slurp_result)

    # Should decode base64 and parse
    assert len(result) == 1
    assert result[0]["source"] == "/dev/sda1"
    assert result[0]["mount"] == "/"
    assert result[0]["type"] == "ext4"


def test_mount_parse_multiline_string(filter_module):
    """Test parsing mount output from multiline string."""
    mount_output = """/dev/sda1 on / type ext4 (rw)
proc on /proc type proc (rw,nosuid,nodev,noexec)"""

    mount_filter = filter_module.filters()["mount"]
    result = mount_filter(mount_output)

    assert len(result) == 2
    assert result[0]["source"] == "/dev/sda1"
    assert result[1]["source"] == "proc"


def test_mount_parse_error_handling(filter_module):
    """Test error handling when parsing fails."""
    mount_filter = filter_module.filters()["mount"]
    with pytest.raises(AnsibleFilterError) as exc_info:
        # Invalid mount output that jc can't parse
        mount_filter("this is not valid mount output")

    assert "mount failed" in str(exc_info.value)


def test_mount_parse_import_error(filter_module):
    """Test error handling when jc is not available."""
    mount_filter = filter_module.filters()["mount"]
    with patch(
        "ansible_collections.o0_o.posix.plugins.module_utils.jc_utils.HAS_JC",
        False,
    ):
        with pytest.raises(AnsibleFilterError) as exc_info:
            mount_filter("mount output")

        assert "jc library is required" in str(exc_info.value)


def test_mount_options_parsing(filter_module):
    """Test parsing of various mount option formats."""
    mount_output = (
        "/dev/sda1 on /mnt type ext4 (rw,uid=1000,gid=1000,umask=0022)"
    )
    mount_filter = filter_module.filters()["mount"]
    result = mount_filter(mount_output)

    assert len(result) == 1
    assert result[0]["options"]["rw"] is True
    assert result[0]["options"]["uid"] == "1000"
    assert result[0]["options"]["gid"] == "1000"
    assert result[0]["options"]["umask"] == "0022"


def test_mount_network_filesystem(filter_module):
    """Test parsing network filesystem mounts."""
    mount_output = (
        "server:/export on /mnt/nfs type nfs "
        "(rw,vers=4.2,rsize=1048576,wsize=1048576)"
    )
    mount_filter = filter_module.filters()["mount"]
    result = mount_filter(mount_output)

    assert len(result) == 1
    assert result[0]["source"] == "server:/export"
    assert result[0]["mount"] == "/mnt/nfs"
    assert result[0]["type"] == "nfs"
    assert result[0]["options"]["vers"] == "4.2"
    assert result[0]["options"]["rsize"] == "1048576"


def test_mount_virtual_filesystem(filter_module):
    """Test parsing virtual filesystem mounts."""
    mount_output = "tmpfs on /dev/shm type tmpfs (rw,nosuid,nodev)"
    mount_filter = filter_module.filters()["mount"]
    result = mount_filter(mount_output)

    assert len(result) == 1
    assert result[0]["source"] == "tmpfs"
    assert result[0]["mount"] == "/dev/shm"
    assert result[0]["type"] == "tmpfs"
    assert result[0]["options"]["rw"] is True
    assert result[0]["options"]["nosuid"] is True


def test_mount_empty_options(filter_module):
    """Test mount entries with no options."""
    mount_output = "/dev/sda1 on / type ext4 ()"
    mount_filter = filter_module.filters()["mount"]
    result = mount_filter(mount_output)

    assert len(result) == 1
    assert result[0]["options"] == {}


def test_mount_multiple_entries(filter_module):
    """Test parsing multiple mount entries."""
    mount_output = """/dev/sda1 on / type ext4 (rw,relatime)
/dev/sda2 on /home type ext4 (rw,relatime,noatime)
proc on /proc type proc (rw,nosuid,nodev,noexec)"""

    mount_filter = filter_module.filters()["mount"]
    result = mount_filter(mount_output)

    assert len(result) == 3
    # Verify each entry has required fields
    for entry in result:
        assert "source" in entry
        assert "mount" in entry
        assert "type" in entry
        assert "options" in entry
        assert isinstance(entry["options"], dict)
