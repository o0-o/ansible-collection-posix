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

from typing import Generator

import pytest

from ansible_collections.o0_o.posix.plugins.action.mounts import ActionModule


@pytest.fixture
def plugin(base) -> Generator[ActionModule, None, None]:
    """Create an ActionModule instance with patched dependencies."""
    base._task.async_val = False
    base._task.action = "mounts"
    base._task.args = {}  # Initialize with empty args

    plugin = ActionModule(
        task=base._task,
        connection=base._connection,
        play_context=base._play_context,
        loader=base._loader,
        templar=base._templar,
        shared_loader_obj=base._shared_loader_obj,
    )

    # Make display available for the test without initialization
    plugin._display = base._display
    plugin.inventory_hostname = "localhost"

    yield plugin


def test_get_mounts_basic(monkeypatch, plugin) -> None:
    """Test basic mount parsing with standard format."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout": """/dev/sda1 on / type ext4 (rw,relatime)
/dev/sda2 on /boot type ext4 (rw,relatime)
proc on /proc type proc (rw,nosuid,nodev,noexec)
tmpfs on /tmp type tmpfs (rw,nosuid,nodev)""",
            }
        elif cmd == "df -P":
            return {
                "rc": 0,
                "stdout": (
                    "Filesystem     1024-blocks    Used Available "
                    "Capacity  Mounted on\n"
                    "/dev/sda1         1024000  512000    512000     "
                    "50%   /\n"
                    "/dev/sda2          512000  256000    256000     "
                    "50%   /boot\n"
                    "tmpfs              512000    1000    511000      "
                    "1%   /tmp"
                ),
            }
        elif cmd == "cat /etc/fstab":
            return {"rc": 0, "stdout": ""}
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_command", mock_cmd)

    mounts = plugin._get_mounts_dict(task_vars={})

    # Should return a dict keyed by mountpoint
    assert isinstance(mounts, dict)

    # By default, virtual filesystems (tmpfs) are filtered out
    # But device filesystems are included
    assert "/" in mounts
    assert "/boot" in mounts
    assert "/tmp" not in mounts  # tmpfs filtered out by default

    # Check root mount details
    root = mounts["/"]
    assert root["source"] == {"path": "/dev/sda1"}
    assert root["type"] == "ext4"
    assert "capacity" in root
    assert root["capacity"]["total"]["bytes"] == 1024000 * 1024
    assert root["capacity"]["used"]["bytes"] == 512000 * 1024
    assert root["options"]["writable"] is True
    assert root["options"]["atime"] == "relative"

    # Check boot mount details
    boot = mounts["/boot"]
    assert boot["source"] == {"path": "/dev/sda2"}
    assert boot["type"] == "ext4"
    assert "capacity" in boot
    assert boot["capacity"]["total"]["bytes"] == 512000 * 1024
    assert boot["capacity"]["used"]["bytes"] == 256000 * 1024


def test_get_mounts_with_virtual_option(monkeypatch, plugin) -> None:
    """Test mount parsing with virtual filesystems included."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout": """/dev/sda1 on / type ext4 (rw,relatime)
proc on /proc type proc (rw,nosuid,nodev,noexec)
tmpfs on /tmp type tmpfs (rw,nosuid,nodev)""",
            }
        elif cmd == "df -P":
            return {
                "rc": 0,
                "stdout": (
                    "Filesystem     1024-blocks    Used Available "
                    "Capacity  Mounted on\n"
                    "/dev/sda1         1024000  512000    512000     "
                    "50%   /\n"
                    "tmpfs              512000    1000    511000      "
                    "1%   /tmp"
                ),
            }
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_command", mock_cmd)
    plugin._task.args = {"virtual": True}

    mounts = plugin._get_mounts_dict(task_vars={})

    # With virtual=True, tmpfs should be included
    assert "/" in mounts
    assert "/tmp" in mounts

    # Check tmpfs mount
    tmp = mounts["/tmp"]
    assert tmp["source"] == {"name": "tmpfs"}
    assert tmp["type"] == "tmpfs"
    assert "capacity" in tmp


def test_get_mounts_with_spaces(monkeypatch, plugin) -> None:
    """Test mount parsing with spaces in paths."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout": (
                    r"/dev/sda1 on /mnt/my\040folder type ext4 "
                    r"(rw,relatime)"
                ),
            }
        elif cmd == "df -P":
            return {
                "rc": 0,
                "stdout": (
                    "Filesystem     1024-blocks      Used Available "
                    "Capacity  Mounted on\n"
                    r"/dev/sda1         1024000    512000    512000     "
                    r"50%   /mnt/my folder"
                ),
            }
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_command", mock_cmd)

    mounts = plugin._get_mounts_dict(task_vars={})

    # JC should handle escaped spaces in mount paths
    assert "/mnt/my folder" in mounts
    mount = mounts["/mnt/my folder"]
    assert mount["source"] == {"path": "/dev/sda1"}


def test_get_mounts_macos_format(monkeypatch, plugin) -> None:
    """Test mount parsing with macOS mount format."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout": "/dev/disk3s1s1 on / (apfs, local, journaled)",
            }
        elif cmd == "df -P":
            return {
                "rc": 0,
                "stdout": (
                    "Filesystem        1024-blocks      Used  Available "
                    "Capacity  Mounted on\n"
                    "/dev/disk3s1s1      500000000 300000000  200000000     "
                    "60%   /"
                ),
            }
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_command", mock_cmd)

    mounts = plugin._get_mounts_dict(task_vars={})

    assert "/" in mounts
    root = mounts["/"]
    assert root["source"] == {"path": "/dev/disk3s1s1"}
    assert root["type"] == "apfs"  # First option in macOS format
    assert root["options"]["local"] is True
    assert root["options"]["journaled"] is True


def test_get_mounts_mount_fails(monkeypatch, plugin) -> None:
    """Test handling of mount command failure."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {"rc": 1, "stderr": "mount: command not found"}
        elif cmd == "df -P":
            return {
                "rc": 0,
                "stdout": (
                    "Filesystem     1024-blocks    Used Available "
                    "Capacity  Mounted on\n"
                    "/dev/sda1         1024000  512000    512000     50%   /"
                ),
            }
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_command", mock_cmd)

    with pytest.raises(Exception) as exc:
        plugin._get_mounts_dict(task_vars={})

    assert "Failed to execute mount command" in str(exc.value)


def test_get_mounts_no_df(monkeypatch, plugin) -> None:
    """Test handling when df is not available."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout": "/dev/sda1 on / type ext4 (rw,relatime)",
            }
        elif cmd == "df -P":
            return {"rc": 1, "stderr": "df: command not found"}
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_command", mock_cmd)

    # df failure should raise an exception since it's required
    with pytest.raises(Exception) as exc:
        plugin._get_mounts_dict(task_vars={})

    assert "Failed to execute df command" in str(exc.value)


def test_get_mounts_virtual_fs_filtering(monkeypatch, plugin) -> None:
    """Test filtering of virtual filesystems."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout": """/dev/sda1 on / type ext4 (rw,relatime)
proc on /proc type proc (rw,nosuid,nodev,noexec)
sysfs on /sys type sysfs (rw,nosuid,nodev,noexec)
devpts on /dev/pts type devpts (rw,nosuid,noexec)
tmpfs on /run type tmpfs (rw,nosuid,nodev)""",
            }
        elif cmd == "df -P":
            return {
                "rc": 0,
                "stdout": (
                    "Filesystem     1024-blocks    Used Available "
                    "Capacity  Mounted on\n"
                    "/dev/sda1         1024000  512000    512000     "
                    "50%   /\n"
                    "tmpfs              512000    1000    511000      "
                    "1%   /run"
                ),
            }
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_command", mock_cmd)

    # Default: virtual=False (exclude virtual filesystems)
    mounts = plugin._get_mounts_dict(task_vars={})

    assert "/" in mounts
    assert "/run" not in mounts  # tmpfs excluded

    # With virtual=True
    plugin._task.args = {"virtual": True}
    mounts = plugin._get_mounts_dict(task_vars={})

    assert "/" in mounts
    assert "/run" in mounts  # tmpfs included


def test_get_mounts_network_fs(monkeypatch, plugin) -> None:
    """Test handling of network filesystems."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout": (
                    "/dev/sda1 on / type ext4 (rw,relatime)\n"
                    "server:/export on /mnt/nfs type nfs "
                    "(rw,vers=4.2,rsize=1048576,wsize=1048576)"
                ),
            }
        elif cmd == "df -P":
            return {
                "rc": 0,
                "stdout": (
                    "Filesystem      1024-blocks     Used Available "
                    "Capacity  Mounted on\n"
                    "/dev/sda1          1024000   512000    512000     "
                    "50%   /\n"
                    "server:/export     2048000  1024000   1024000     "
                    "50%   /mnt/nfs"
                ),
            }
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_command", mock_cmd)

    # Default: network=True (include network filesystems)
    mounts = plugin._get_mounts_dict(task_vars={})

    assert "/" in mounts
    assert "/mnt/nfs" in mounts

    nfs_mount = mounts["/mnt/nfs"]
    assert nfs_mount["source"] == {"address": "server:/export"}
    assert nfs_mount["type"] == "nfs"
    assert nfs_mount["options"]["vers"] == "4.2"

    # With network=False
    plugin._task.args = {"network": False}
    mounts = plugin._get_mounts_dict(task_vars={})

    assert "/" in mounts
    assert "/mnt/nfs" not in mounts  # NFS excluded


def test_run_method(monkeypatch, plugin) -> None:
    """Test the main run method."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout": "/dev/sda1 on / type ext4 (rw,relatime)",
            }
        elif cmd == "df -P":
            return {
                "rc": 0,
                "stdout": (
                    "Filesystem     1024-blocks    Used Available "
                    "Capacity  Mounted on\n"
                    "/dev/sda1         1024000  512000    512000     50%   /"
                ),
            }
        elif cmd == "cat /etc/fstab":
            return {
                "rc": 0,
                "stdout": (
                    "/dev/sda1    /    ext4    defaults    0    1\n"
                    "/dev/sda2    /home    ext4    defaults    0    2"
                ),
            }
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_command", mock_cmd)

    result = plugin.run(task_vars={})

    assert result["changed"] is False
    assert "mounts" in result
    assert isinstance(result["mounts"], dict)
    assert "/" in result["mounts"]
    assert result["mounts"]["/"]["source"] == {"path": "/dev/sda1"}
    assert "fstab" in result
    assert isinstance(result["fstab"], list)
    assert len(result["fstab"]) == 2
    assert result["fstab"][0]["mount"] == "/"
    assert result["fstab"][1]["mount"] == "/home"
