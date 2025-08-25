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

from ansible_collections.o0_o.posix.plugins.action.facts import ActionModule


@pytest.fixture
def plugin(base) -> Generator[ActionModule, None, None]:
    """Create an ActionModule instance with patched dependencies."""
    base._task.async_val = False
    base._task.action = "facts"

    plugin = ActionModule(
        task=base._task,
        connection=base._connection,
        play_context=base._play_context,
        loader=base._loader,
        templar=base._templar,
        shared_loader_obj=base._shared_loader_obj,
    )
    plugin._cmd = base._cmd
    plugin._display = base._display
    return plugin


def test_get_mounts_basic(monkeypatch, plugin) -> None:
    """Test basic mount parsing with standard format."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout_lines": [
                    "/dev/sda1 on / type ext4 (rw,relatime)",
                    "/dev/sda2 on /boot type ext4 (rw,relatime)",
                    "tmpfs on /tmp type tmpfs (rw,nosuid,nodev)",
                    "proc on /proc type proc (rw,nosuid,nodev,noexec,relatime)",
                ],
            }
        elif cmd == "df -P":
            return {
                "rc": 0,
                "stdout_lines": [
                    "Filesystem     1024-blocks      Used Available Capacity  Mounted on",
                    "/dev/sda1       102400000  51200000  51200000      50%  /",
                    "/dev/sda2         1024000    512000    512000      50%  /boot",
                    "tmpfs             8192000   1024000   7168000      13%  /tmp",
                    "proc                    0         0         0       0%  /proc",
                ],
            }
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    mounts = plugin._get_mounts(task_vars={})

    # proc and tmpfs are filtered out as virtual filesystems
    assert len(mounts) == 2
    assert "/" in mounts
    assert "/boot" in mounts

    # Check root mount
    root_mount = mounts["/"]
    assert root_mount["device"] == "/dev/sda1"
    assert root_mount["filesystem"] == "ext4"
    assert root_mount["options"] == ["rw", "relatime"]
    assert root_mount["capacity"]["total"]["value"] == 102400000 * 1024
    assert root_mount["capacity"]["used"]["value"] == 51200000 * 1024
    assert "available" not in root_mount["capacity"]
    assert "percent_used" not in root_mount["capacity"]

    # Check /boot mount
    boot_mount = mounts["/boot"]
    assert boot_mount["device"] == "/dev/sda2"
    assert boot_mount["filesystem"] == "ext4"
    assert "percent_used" not in boot_mount["capacity"]

    # tmpfs should be filtered out
    assert "/tmp" not in mounts


def test_get_mounts_macos_format(monkeypatch, plugin) -> None:
    """Test parsing macOS-style mount output."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout_lines": [
                    "/dev/disk3s1s1 on / (apfs, sealed, local, read-only, journaled)",
                    "devfs on /dev (devfs, local, nobrowse)",
                    "/dev/disk3s5 on /System/Volumes/Data (apfs, local, journaled, nobrowse)",
                ],
            }
        elif cmd == "df -P":
            return {
                "rc": 0,
                "stdout_lines": [
                    "Filesystem     512-blocks       Used  Available Capacity  Mounted on",
                    "/dev/disk3s1s1 7805330720   22000424 1983696096     2%    /",
                    "devfs                 742        742          0   100%    /dev",
                    "/dev/disk3s5   7805330720 5782744992 1983696096    75%    /System/Volumes/Data",
                ],
            }
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    mounts = plugin._get_mounts(task_vars={})

    # devfs is filtered out as virtual filesystem
    assert len(mounts) == 2

    # Check root mount
    assert "/" in mounts
    root_mount = mounts["/"]
    assert root_mount["device"] == "/dev/disk3s1s1"
    assert root_mount["filesystem"] == "apfs"
    assert "sealed" in root_mount["options"]
    assert "local" in root_mount["options"]
    assert "read-only" in root_mount["options"]
    # 512-byte blocks
    assert root_mount["capacity"]["total"]["value"] == 7805330720 * 512
    assert "percent_used" not in root_mount["capacity"]

    # devfs should be filtered out
    assert "/dev" not in mounts


def test_get_mounts_with_spaces(monkeypatch, plugin) -> None:
    """Test handling mount points with spaces."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout_lines": [
                    "/dev/sda1 on /mnt/my files type ext4 (rw)",
                ],
            }
        elif cmd == "df -P":
            return {
                "rc": 0,
                "stdout_lines": [
                    "Filesystem     1024-blocks  Used Available Capacity  Mounted on",
                    "/dev/sda1         1024000 512000    512000      50%  /mnt/my files",
                ],
            }
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    mounts = plugin._get_mounts(task_vars={})

    assert len(mounts) == 1
    assert "/mnt/my files" in mounts
    assert mounts["/mnt/my files"]["device"] == "/dev/sda1"


def test_get_mounts_df_only(monkeypatch, plugin) -> None:
    """Test when mount command fails but df works."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {"rc": 1, "stderr": "mount: command not found"}
        elif cmd == "df -P":
            return {
                "rc": 0,
                "stdout_lines": [
                    "Filesystem     1024-blocks  Used Available Capacity  Mounted on",
                    "/dev/sda1         1024000 512000    512000      50%  /",
                    "tmpfs              512000  1000    511000       1%  /tmp",
                ],
            }
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    mounts = plugin._get_mounts(task_vars={})

    # Without mount info, we can't determine filesystem type so we skip entries
    assert len(mounts) == 0


def test_get_mounts_both_fail(monkeypatch, plugin) -> None:
    """Test when both mount and df commands fail."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        return {"rc": 1, "stderr": "command not found"}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    mounts = plugin._get_mounts(task_vars={})

    assert mounts == {}


def test_get_mounts_exception_handling(monkeypatch, plugin) -> None:
    """Test exception handling in mount gathering."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        raise RuntimeError("Connection error")

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    mounts = plugin._get_mounts(task_vars={})

    assert mounts == {}


def test_get_mounts_virtual_fs_filtering(monkeypatch, plugin) -> None:
    """Test that virtual filesystems are properly filtered out."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout_lines": [
                    "/dev/sda1 on / type ext4 (rw,relatime)",
                    "proc on /proc type proc (rw,nosuid,nodev,noexec)",
                    "sysfs on /sys type sysfs (rw,nosuid,nodev,noexec)",
                    "devfs on /dev type devfs (rw,nosuid)",
                    "tmpfs on /run type tmpfs (rw,nosuid,nodev)",
                    "overlay on /var/lib/docker type overlay (rw)",
                    "/dev/sdb1 on /data type xfs (rw,relatime)",
                ],
            }
        elif cmd == "df -P":
            return {
                "rc": 0,
                "stdout_lines": [
                    "Filesystem     1024-blocks  Used Available Capacity  Mounted on",
                    "/dev/sda1         1000000 500000    500000      50%  /",
                    "proc                    0      0         0       0%  /proc",
                    "sysfs                   0      0         0       0%  /sys",
                    "devfs                 100    100         0     100%  /dev",
                    "tmpfs              500000  10000    490000       2%  /run",
                    "overlay           1000000 100000    900000      10%  /var/lib/docker",
                    "/dev/sdb1         2000000 1000000  1000000      50%  /data",
                ],
            }
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    mounts = plugin._get_mounts(task_vars={})

    # Should only have real filesystems (ext4, xfs), not virtual ones
    assert len(mounts) == 2

    assert "/" in mounts
    assert "/data" in mounts

    # Virtual filesystems should be filtered
    assert "/proc" not in mounts
    assert "/sys" not in mounts
    assert "/dev" not in mounts
    assert "/run" not in mounts
    assert "/var/lib/docker" not in mounts

    # Check the remaining mounts have correct info
    assert mounts["/"]["filesystem"] == "ext4"
    assert mounts["/"]["capacity"]["total"]["value"] == 1000000 * 1024

    assert mounts["/data"]["filesystem"] == "xfs"
    assert mounts["/data"]["capacity"]["used"]["value"] == 1000000 * 1024


def test_get_mounts_sorting(monkeypatch, plugin) -> None:
    """Test that mounts are sorted by mount point."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout_lines": [
                    "/dev/sda2 on /var type ext4 (rw)",
                    "/dev/sda1 on / type ext4 (rw)",
                    "/dev/sda3 on /home type ext4 (rw)",
                    "/dev/sda4 on /boot type ext4 (rw)",
                ],
            }
        elif cmd == "df -P":
            return {"rc": 0, "stdout_lines": ["Filesystem 1024-blocks Used Available Capacity Mounted on"]}
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    mounts = plugin._get_mounts(task_vars={})

    # Dict keys maintain insertion order, which should be sorted by mount point
    mount_points = list(mounts.keys())
    assert mount_points == ["/", "/boot", "/home", "/var"]
