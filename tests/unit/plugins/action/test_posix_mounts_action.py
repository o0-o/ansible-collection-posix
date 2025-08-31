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

    yield plugin


def test_get_mounts_basic(monkeypatch, plugin) -> None:
    """Test basic mount parsing with standard format."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout_lines": [
                    "/dev/sda1 on / type ext4 (rw,relatime)",
                    "/dev/sda2 on /boot type ext4 (rw,relatime)",
                    "proc on /proc type proc (rw,nosuid,nodev,noexec)",
                    "tmpfs on /tmp type tmpfs (rw,nosuid,nodev)",
                ],
            }
        elif cmd == "df -P":
            return {
                "rc": 0,
                "stdout_lines": [
                    "Filesystem     1024-blocks  Used Available Capacity  Mounted on",
                    "/dev/sda1         1024000 512000    512000      50%  /",
                    "/dev/sda2          512000 256000    256000      50%  /boot",
                    "tmpfs              512000  1000    511000       1%  /tmp",
                ],
            }
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    mounts = plugin._get_mounts(task_vars={})

    # proc and tmpfs are filtered out as virtual filesystems by default
    assert len(mounts) == 2
    assert "/" in mounts
    assert "/boot" in mounts

    # Check root mount details
    root = mounts["/"]
    assert root["source"] == "/dev/sda1"
    assert root["type"] == "device"
    assert root["filesystem"] == "ext4"
    assert root["options"] == ["rw", "relatime"]
    assert "capacity" in root
    assert "total" in root["capacity"]
    assert "used" in root["capacity"]

    # Check boot mount details
    boot = mounts["/boot"]
    assert boot["source"] == "/dev/sda2"
    assert boot["type"] == "device"
    assert boot["filesystem"] == "ext4"
    assert boot["options"] == ["rw", "relatime"]
    assert "capacity" in boot


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
    assert "/" in mounts
    assert "/System/Volumes/Data" in mounts

    # Check root mount
    root = mounts["/"]
    assert root["source"] == "/dev/disk3s1s1"
    assert root["type"] == "device"
    assert root["filesystem"] == "apfs"
    assert "sealed" in root["options"]
    assert "local" in root["options"]
    assert "capacity" in root

    # Check data volume
    data = mounts["/System/Volumes/Data"]
    assert data["source"] == "/dev/disk3s5"
    assert data["type"] == "device"
    assert data["filesystem"] == "apfs"
    assert "local" in data["options"]
    assert "capacity" in data


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
    assert "capacity" in mounts["/mnt/my files"]


def test_get_mounts_mount_fails(monkeypatch, plugin) -> None:
    """Test when mount command fails."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            raise Exception("mount: command not found")
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    # Should raise because mount command is required
    with pytest.raises(Exception) as exc_info:
        plugin._get_mounts(task_vars={})

    assert "Failed to execute mount command" in str(exc_info.value)


def test_get_mounts_no_df(monkeypatch, plugin) -> None:
    """Test when df command fails but mount works."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout_lines": [
                    "/dev/sda1 on / type ext4 (rw,relatime)",
                    "/dev/sda2 on /boot type ext4 (rw,relatime)",
                ],
            }
        elif cmd == "df -P":
            raise Exception("df: command not found")
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    mounts = plugin._get_mounts(task_vars={})

    # Should work without df, just no capacity info
    assert len(mounts) == 2
    assert "/" in mounts
    assert "/boot" in mounts

    # No capacity info without df
    assert "capacity" not in mounts["/"]
    assert "capacity" not in mounts["/boot"]


def test_get_mounts_virtual_fs_filtering(monkeypatch, plugin) -> None:
    """Test that virtual filesystems are properly filtered out."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout_lines": [
                    "/dev/sda1 on / type ext4 (rw)",
                    "/dev/sda2 on /data type xfs (rw)",
                    "proc on /proc type proc (rw)",
                    "sysfs on /sys type sysfs (rw)",
                    "devfs on /dev type devfs (rw)",
                    "tmpfs on /tmp type tmpfs (rw)",
                    "cgroup on /sys/fs/cgroup type cgroup2 (rw)",
                    "debugfs on /sys/kernel/debug type debugfs (rw)",
                    "securityfs on /sys/kernel/security type securityfs (rw)",
                    "pstore on /sys/fs/pstore type pstore (rw)",
                    "efivarfs on /sys/firmware/efi/efivars type efivarfs (rw)",
                    "bpf on /sys/fs/bpf type bpf (rw)",
                    "tracefs on /sys/kernel/tracing type tracefs (rw)",
                    "hugetlbfs on /dev/hugepages type hugetlbfs (rw)",
                    "mqueue on /dev/mqueue type mqueue (rw)",
                    "fusectl on /sys/fs/fuse/connections type fusectl (rw)",
                ],
            }
        elif cmd == "df -P":
            return {"rc": 0, "stdout_lines": []}
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    mounts = plugin._get_mounts(task_vars={})

    # Should only have real filesystems (ext4, xfs), not virtual ones
    assert len(mounts) == 2
    assert "/" in mounts
    assert "/data" in mounts

    # Virtual filesystems should be filtered out
    assert "/proc" not in mounts
    assert "/sys" not in mounts
    assert "/dev" not in mounts
    assert "/tmp" not in mounts
    assert "/sys/fs/cgroup" not in mounts
    assert "/sys/kernel/debug" not in mounts
    assert "/sys/kernel/security" not in mounts
    assert "/sys/fs/pstore" not in mounts
    assert "/sys/firmware/efi/efivars" not in mounts


def test_get_mounts_with_virtual_option(monkeypatch, plugin) -> None:
    """Test including virtual filesystems with option."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout_lines": [
                    "/dev/sda1 on / type ext4 (rw)",
                    "tmpfs on /tmp type tmpfs (rw)",
                    "proc on /proc type proc (rw)",
                ],
            }
        elif cmd == "df -P":
            return {"rc": 0, "stdout_lines": []}
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    # Set virtual=True to include virtual filesystems
    plugin._task.args["virtual"] = True

    mounts = plugin._get_mounts(task_vars={})

    # Should include all filesystems
    assert len(mounts) == 3
    assert "/" in mounts
    assert "/tmp" in mounts
    assert "/proc" in mounts

    # Check type classification
    assert mounts["/"]["type"] == "device"
    assert mounts["/tmp"]["type"] == "virtual"
    assert mounts["/tmp"]["source"] == "tmpfs"
    assert mounts["/proc"]["type"] == "virtual"
    assert mounts["/proc"]["source"] == "proc"


def test_get_mounts_network_fs(monkeypatch, plugin) -> None:
    """Test network filesystem handling."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout_lines": [
                    "/dev/sda1 on / type ext4 (rw)",
                    "nfs-server:/export/home on /mnt/nfs type nfs (rw,vers=4.0)",
                    "//cifs-server/share on /mnt/cifs type cifs (rw,vers=3.0)",
                ],
            }
        elif cmd == "df -P":
            return {"rc": 0, "stdout_lines": []}
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    # Default includes network filesystems
    mounts = plugin._get_mounts(task_vars={})

    assert len(mounts) == 3
    assert "/" in mounts
    assert "/mnt/nfs" in mounts
    assert "/mnt/cifs" in mounts

    # Check NFS mount
    nfs = mounts["/mnt/nfs"]
    assert nfs["source"] == "nfs-server:/export/home"
    assert nfs["type"] == "network"
    assert nfs["filesystem"] == "nfs"

    # Check CIFS mount
    cifs = mounts["/mnt/cifs"]
    assert cifs["source"] == "//cifs-server/share"
    assert cifs["type"] == "network"
    assert cifs["filesystem"] == "cifs"

    # Now exclude network filesystems
    plugin._task.args["network"] = False
    mounts = plugin._get_mounts(task_vars={})

    assert len(mounts) == 1
    assert "/" in mounts
    assert "/mnt/nfs" not in mounts
    assert "/mnt/cifs" not in mounts


def test_run_method(monkeypatch, plugin) -> None:
    """Test the main run method."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout_lines": [
                    "/dev/sda1 on / type ext4 (rw,relatime)",
                    "/dev/sda2 on /boot type ext4 (rw,relatime)",
                ],
            }
        elif cmd == "df -P":
            return {
                "rc": 0,
                "stdout_lines": [
                    "Filesystem     1024-blocks  Used Available Capacity  Mounted on",
                    "/dev/sda1         1024000 512000    512000      50%  /",
                    "/dev/sda2          512000 256000    256000      25%  /boot",
                ],
            }
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    result = plugin.run(task_vars={})

    assert result["changed"] is False
    assert "mounts" in result
    assert len(result["mounts"]) == 2
    assert "/" in result["mounts"]
    assert "/boot" in result["mounts"]

    # Check that capacity was merged from df
    assert "capacity" in result["mounts"]["/"]
    assert "capacity" in result["mounts"]["/boot"]

    # Capacity should have the proper structure
    assert "total" in result["mounts"]["/"]["capacity"]
    assert "used" in result["mounts"]["/"]["capacity"]
