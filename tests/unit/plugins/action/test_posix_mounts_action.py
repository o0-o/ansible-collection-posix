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
from ansible_collections.o0_o.posix.tests.utils import find_mount_by_target


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
                "stdout": """\n/dev/sda1 on / type ext4 (rw,relatime)
/dev/sda2 on /boot type ext4 (rw,relatime)
proc on /proc type proc (rw,nosuid,nodev,noexec)
tmpfs on /tmp type tmpfs (rw,nosuid,nodev)""".strip(),
            }
        elif cmd == "df -P":
            return {
                "rc": 0,
                "stdout": (
                    "Filesystem     1024-blocks  Used Available "
                    "Capacity  Mounted on\n"
                    "/dev/sda1         1024000 512000    512000      50%  /\n"
                    "/dev/sda2          512000 256000    256000      50%  "
                    "/boot\n"
                    "tmpfs              512000  1000    511000       1%  /tmp"
                ),
            }
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    mounts = plugin._get_mounts(task_vars={})

    # proc and tmpfs are filtered out as virtual filesystems by default
    assert len(mounts) == 2
    
    # Find mounts by target
    root = find_mount_by_target(mounts, "/")
    boot = find_mount_by_target(mounts, "/boot")
    
    assert root is not None
    assert boot is not None
    
    # Check root mount details
    assert root["source"] == "/dev/sda1"
    assert root["type"] == "regular"
    assert root["driver"] == "ext4"
    assert root["options"] == {"rw": True, "relatime": True}
    assert root["fuse"] is False
    assert "capacity" in root
    assert "total" in root["capacity"]
    assert "used" in root["capacity"]

    # Check boot mount details
    assert boot["source"] == "/dev/sda2"
    assert boot["type"] == "regular"
    assert boot["driver"] == "ext4"
    assert boot["options"] == {"rw": True, "relatime": True}
    assert boot["fuse"] is False
    assert "capacity" in boot


def test_get_mounts_macos_format(monkeypatch, plugin) -> None:
    """Test parsing macOS-style mount output."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout": (
                    "/dev/disk3s1s1 on / "
                    "(apfs, sealed, local, read-only, journaled)\n"
                    "devfs on /dev (devfs, local, nobrowse)\n"
                    "/dev/disk3s5 on /System/Volumes/Data "
                    "(apfs, local, journaled, nobrowse)"
                ),
            }
        elif cmd == "df -P":
            return {
                "rc": 0,
                "stdout": (
                    "Filesystem     512-blocks       Used  Available "
                    "Capacity  Mounted on\n"
                    "/dev/disk3s1s1 7805330720   22000424 1983696096     "
                    "2%    /\n"
                    "devfs                 742        742          0   "
                    "100%    /dev\n"
                    "/dev/disk3s5   7805330720 5782744992 1983696096    "
                    "75%    "
                    "/System/Volumes/Data"
                ),
            }
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    mounts = plugin._get_mounts(task_vars={})

    # devfs is filtered out as virtual filesystem
    assert len(mounts) == 2
    
    # Find mounts by target
    root = find_mount_by_target(mounts, "/")
    data = find_mount_by_target(mounts, "/System/Volumes/Data")
    
    assert root is not None
    assert data is not None
    
    # Check root mount
    assert root["source"] == "/dev/disk3s1s1"
    assert root["type"] == "regular"
    assert root["driver"] == "apfs"
    assert root["options"]["sealed"] is True
    assert root["options"]["local"] is True
    assert root["fuse"] is False
    assert "capacity" in root

    # Check data volume
    assert data["source"] == "/dev/disk3s5"
    assert data["type"] == "regular"
    assert data["driver"] == "apfs"
    assert data["options"]["local"] is True
    assert data["fuse"] is False
    assert "capacity" in data


def test_get_mounts_with_spaces(monkeypatch, plugin) -> None:
    """Test handling mount points with spaces."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout": "/dev/sda1 on /mnt/my files type ext4 (rw)",
            }
        elif cmd == "df -P":
            return {
                "rc": 0,
                "stdout": (
                    "Filesystem     1024-blocks  Used Available "
                    "Capacity  Mounted on\n"
                    "/dev/sda1         1024000 512000    512000      50%  "
                    "/mnt/my files"
                ),
            }
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    mounts = plugin._get_mounts(task_vars={})

    assert len(mounts) == 1
    mount = find_mount_by_target(mounts, "/mnt/my files")
    assert mount is not None
    assert "capacity" in mount


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
                "stdout": """/dev/sda1 on / type ext4 (rw,relatime)
/dev/sda2 on /boot type ext4 (rw,relatime)""",
            }
        elif cmd == "df -P":
            raise Exception("df: command not found")
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    mounts = plugin._get_mounts(task_vars={})

    # Should work without df, just no capacity info
    assert len(mounts) == 2
    root = find_mount_by_target(mounts, "/")
    boot = find_mount_by_target(mounts, "/boot")
    assert root is not None
    assert boot is not None

    # No capacity info without df
    assert "capacity" not in root
    assert "capacity" not in boot


def test_get_mounts_virtual_fs_filtering(monkeypatch, plugin) -> None:
    """Test that virtual filesystems are properly filtered out."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout": """/dev/sda1 on / type ext4 (rw)
/dev/sda2 on /data type xfs (rw)
proc on /proc type proc (rw)
sysfs on /sys type sysfs (rw)
devfs on /dev type devfs (rw)
tmpfs on /tmp type tmpfs (rw)
cgroup on /sys/fs/cgroup type cgroup2 (rw)
debugfs on /sys/kernel/debug type debugfs (rw)
securityfs on /sys/kernel/security type securityfs (rw)
pstore on /sys/fs/pstore type pstore (rw)
efivarfs on /sys/firmware/efi/efivars type efivarfs (rw)
bpf on /sys/fs/bpf type bpf (rw)
tracefs on /sys/kernel/tracing type tracefs (rw)
hugetlbfs on /dev/hugepages type hugetlbfs (rw)
mqueue on /dev/mqueue type mqueue (rw)
fusectl on /sys/fs/fuse/connections type fusectl (rw)""",
            }
        elif cmd == "df -P":
            return {"rc": 0, "stdout": ""}
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    mounts = plugin._get_mounts(task_vars={})

    # Should only have real filesystems (ext4, xfs), not virtual ones
    assert len(mounts) == 2
    root = find_mount_by_target(mounts, "/")
    data = find_mount_by_target(mounts, "/data")
    assert root is not None
    assert data is not None

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
                "stdout": """/dev/sda1 on / type ext4 (rw)
tmpfs on /tmp type tmpfs (rw)
proc on /proc type proc (rw)""",
            }
        elif cmd == "df -P":
            return {"rc": 0, "stdout": ""}
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    # Set virtual=True to include virtual filesystems
    plugin._task.args["virtual"] = True

    mounts = plugin._get_mounts(task_vars={})

    # Should include all filesystems
    assert len(mounts) == 3
    
    # Check type classification
    root = find_mount_by_target(mounts, "/")
    tmp = find_mount_by_target(mounts, "/tmp")
    proc = find_mount_by_target(mounts, "/proc")
    
    assert root is not None
    assert tmp is not None
    assert proc is not None
    
    assert root["type"] == "regular"
    assert tmp["type"] == "virtual"
    assert tmp["source"] is None  # Virtual filesystems have source=None
    assert proc["type"] == "virtual"
    assert proc["source"] == "kernel"  # proc is a pseudo filesystem


def test_get_mounts_network_fs(monkeypatch, plugin) -> None:
    """Test network filesystem handling."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout": """/dev/sda1 on / type ext4 (rw)
nfs-server:/export/home on /mnt/nfs type nfs (rw,vers=4.0)
//cifs-server/share on /mnt/cifs type cifs (rw,vers=3.0)""",
            }
        elif cmd == "df -P":
            return {"rc": 0, "stdout": ""}
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    # Default includes network filesystems
    mounts = plugin._get_mounts(task_vars={})

    assert len(mounts) == 3
    
    # Check NFS mount
    nfs = find_mount_by_target(mounts, "/mnt/nfs")
    assert nfs is not None
    assert nfs["source"] == "nfs-server:/export/home"
    assert nfs["type"] == "network"
    assert nfs["driver"] == "nfs"

    # Check CIFS mount  
    cifs = find_mount_by_target(mounts, "/mnt/cifs")
    assert cifs is not None
    assert cifs["source"] == "//cifs-server/share"
    assert cifs["type"] == "network"
    assert cifs["driver"] == "cifs"

    # Now exclude network filesystems
    plugin._task.args["network"] = False
    mounts = plugin._get_mounts(task_vars={})

    assert len(mounts) == 1
    assert find_mount_by_target(mounts, "/") is not None
    assert find_mount_by_target(mounts, "/mnt/nfs") is None
    assert find_mount_by_target(mounts, "/mnt/cifs") is None


def test_run_method(monkeypatch, plugin) -> None:
    """Test the main run method."""

    def mock_cmd(cmd, task_vars=None, **kwargs):
        if cmd == "mount":
            return {
                "rc": 0,
                "stdout": """/dev/sda1 on / type ext4 (rw,relatime)
/dev/sda2 on /boot type ext4 (rw,relatime)""",
            }
        elif cmd == "df -P":
            return {
                "rc": 0,
                "stdout": (
                    "Filesystem     1024-blocks  Used Available "
                    "Capacity  Mounted on\n"
                    "/dev/sda1         1024000 512000    512000      50%  /\n"
                    "/dev/sda2          512000 256000    256000      25%  "
                    "/boot"
                ),
            }
        return {"rc": 1}

    monkeypatch.setattr(plugin, "_cmd", mock_cmd)

    result = plugin.run(task_vars={})

    assert result["changed"] is False
    assert "mounts" in result
    assert len(result["mounts"]) == 2
    
    # Find mounts by target
    root = find_mount_by_target(result["mounts"], "/")
    boot = find_mount_by_target(result["mounts"], "/boot")
    
    assert root is not None
    assert boot is not None
    
    # Check that capacity was merged from df
    assert "capacity" in root
    assert "capacity" in boot

    # Capacity should have the proper structure
    assert "total" in root["capacity"]
    assert "used" in root["capacity"]
