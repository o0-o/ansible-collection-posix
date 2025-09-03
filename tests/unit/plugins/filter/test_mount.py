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

from typing import Any, Dict

import pytest

from ansible_collections.o0_o.posix.plugins.filter.mount import FilterModule


@pytest.fixture
def filter_module() -> FilterModule:
    """Create a FilterModule instance for testing."""
    return FilterModule()


class TestMountParsing:
    """Test mount filter with parametrized test cases."""

    @pytest.mark.parametrize(
        "mount_output,expected_count,first_mount",
        [
            # Standard Linux mounts
            (
                """/dev/sda1 on / type ext4 (rw,relatime,errors=remount-ro)
/dev/sda2 on /boot type ext4 (rw,relatime)""",
                2,
                {
                    "filesystem": "/dev/sda1",
                    "mount_point": "/",
                    "type": "ext4",
                    "options": ["rw", "relatime", "errors=remount-ro"],
                },
            ),
            # macOS style without 'type' keyword
            (
                """/dev/disk3s1s1 on / (apfs, sealed, local, read-only, journaled)
devfs on /dev (devfs, local, nobrowse)""",
                2,
                {
                    "filesystem": "/dev/disk3s1s1",
                    "mount_point": "/",
                    # First option is the type on macOS
                    "options": ["apfs", "sealed", "local", "read-only", "journaled"],
                },
            ),
            # Empty input
            ("", 0, None),
            # Single mount
            (
                "/dev/sda1 on / type ext4 (rw)",
                1,
                {
                    "filesystem": "/dev/sda1",
                    "mount_point": "/",
                    "type": "ext4",
                    "options": ["rw"],
                },
            ),
        ],
    )
    def test_raw_parsing(
        self,
        filter_module: FilterModule,
        mount_output: str,
        expected_count: int,
        first_mount: Dict[str, Any],
    ) -> None:
        """Test raw mount parsing (facts=False)."""
        result = filter_module.mount(mount_output)
        assert len(result) == expected_count

        if first_mount:
            # Check key fields of first mount
            assert result[0]["filesystem"] == first_mount["filesystem"]
            assert result[0]["mount_point"] == first_mount["mount_point"]
            # Check options are present (order may vary)
            for opt in first_mount["options"]:
                assert opt in result[0]["options"]
            # Type field may or may not be present depending on OS
            if "type" in first_mount:
                assert result[0]["type"] == first_mount["type"]

    @pytest.mark.parametrize(
        "mount_output,mount_point,expected_facts",
        [
            # Device mount
            (
                "/dev/sda1 on / type ext4 (rw,relatime)",
                "/",
                {
                    "source": "/dev/sda1",
                    "type": "device",
                    "filesystem": "ext4",
                    "fuse": False,
                    "options": {"rw": True, "relatime": True},
                },
            ),
            # Virtual filesystem - tmpfs
            (
                "tmpfs on /dev/shm type tmpfs (rw,nosuid,nodev)",
                "/dev/shm",
                {
                    "source": None,
                    "type": "virtual",
                    "filesystem": "tmpfs",
                    "pseudo": False,  # tmpfs is virtual but not pseudo
                    "fuse": False,
                    "options": {"rw": True, "nosuid": True, "nodev": True},
                },
            ),
            # Pseudo filesystem - proc
            (
                "proc on /proc type proc (rw,nosuid,nodev,noexec,relatime)",
                "/proc",
                {
                    "source": None,
                    "type": "virtual",
                    "filesystem": "proc",
                    "pseudo": True,  # proc is a pseudo filesystem
                    "fuse": False,
                    "options": {
                        "rw": True,
                        "nosuid": True,
                        "nodev": True,
                        "noexec": True,
                        "relatime": True,
                    },
                },
            ),
            # Network filesystem - NFS
            (
                "server:/export on /mnt/nfs type nfs (rw,vers=4.2,rsize=1048576)",
                "/mnt/nfs",
                {
                    "source": "server:/export",
                    "type": "network",
                    "filesystem": "nfs",
                    "fuse": False,
                    "options": {"rw": True, "vers": "4.2", "rsize": "1048576"},
                },
            ),
            # Network filesystem - CIFS
            (
                "//server/share on /mnt/smb type cifs (rw,uid=1000,gid=1000)",
                "/mnt/smb",
                {
                    "source": "//server/share",
                    "type": "network",
                    "filesystem": "cifs",
                    "fuse": False,
                    "options": {"rw": True, "uid": "1000", "gid": "1000"},
                },
            ),
            # Overlay filesystem (Docker root)
            (
                "overlay on / type overlay (rw,relatime,lowerdir=/var/lib/docker/overlay2/l/ABC:/var/lib/docker/overlay2/l/DEF,upperdir=/var/lib/docker/overlay2/xyz/diff,workdir=/var/lib/docker/overlay2/xyz/work)",
                "/",
                {
                    # No source field for overlay
                    "type": "overlay",
                    "filesystem": "overlay",
                    "fuse": False,
                    "options": {
                        "rw": True,
                        "relatime": True,
                        "lowerdir": "/var/lib/docker/overlay2/l/ABC:/var/lib/docker/overlay2/l/DEF",
                        "upperdir": "/var/lib/docker/overlay2/xyz/diff",
                        "workdir": "/var/lib/docker/overlay2/xyz/work",
                    },
                },
            ),
            # Bind mount
            (
                "/dev/sda1 on /mnt/bind type ext4 (rw,relatime,bind)",
                "/mnt/bind",
                {
                    "source": "/dev/sda1",
                    "type": "overlay",  # bind mounts are classified as overlay
                    "filesystem": "ext4",
                    "fuse": False,
                    "options": {"rw": True, "relatime": True, "bind": True},
                },
            ),
            # FUSE filesystem with subtype
            (
                "portal on /mnt/portal type fuse (rw,nosuid,nodev,subtype=sshfs)",
                "/mnt/portal",
                {
                    "source": "portal",
                    "type": "network",  # sshfs is network type
                    "filesystem": "sshfs",  # subtype replaces generic fuse
                    "fuse": True,
                    "options": {"rw": True, "nosuid": True, "nodev": True},
                },
            ),
            # FUSE filesystem with fuse. prefix
            (
                "encfs on /mnt/enc type fuse.encfs (rw,nosuid,nodev)",
                "/mnt/enc",
                {
                    "source": "encfs",
                    "filesystem": "fuse.encfs",
                    "fuse": True,
                    "options": {"rw": True, "nosuid": True, "nodev": True},
                },
            ),
            # fuseblk (NTFS)
            (
                "/dev/sda1 on /mnt/ntfs type fuseblk (rw,relatime,allow_other)",
                "/mnt/ntfs",
                {
                    "source": "/dev/sda1",
                    "type": "device",  # fuseblk is device type
                    # No filesystem field when fuseblk without subtype
                    "fuse": True,
                    "options": {"rw": True, "relatime": True, "allow_other": True},
                },
            ),
            # Source as 'none'
            (
                "none on /proc type proc (rw)",
                "/proc",
                {
                    "source": None,  # 'none' becomes None
                    "type": "virtual",
                    "filesystem": "proc",
                    "pseudo": True,
                    "fuse": False,
                    "options": {"rw": True},
                },
            ),
            # Source as '-'
            (
                "- on /sys type sysfs (rw)",
                "/sys",
                {
                    "source": None,  # '-' becomes None
                    "type": "virtual",
                    "filesystem": "sysfs",
                    "pseudo": True,
                    "fuse": False,
                    "options": {"rw": True},
                },
            ),
        ],
    )
    def test_facts_mode(
        self,
        filter_module: FilterModule,
        mount_output: str,
        mount_point: str,
        expected_facts: Dict[str, Any],
    ) -> None:
        """Test mount filter in facts mode."""
        facts = filter_module.mount(mount_output, facts=True)
        assert "mounts" in facts
        assert mount_point in facts["mounts"]

        mount_facts = facts["mounts"][mount_point]

        # Check all expected fields
        for key, expected_value in expected_facts.items():
            if key == "source" and "source" not in expected_facts:
                # Source field may not exist (e.g., overlay)
                assert key not in mount_facts
            else:
                assert mount_facts[key] == expected_value

    @pytest.mark.parametrize(
        "mount_output,expected_mounts",
        [
            # Multiple virtual filesystems
            (
                """proc on /proc type proc (rw)
sysfs on /sys type sysfs (rw)
devpts on /dev/pts type devpts (rw,gid=5,mode=620)
tmpfs on /run type tmpfs (rw,mode=755)
cgroup2 on /sys/fs/cgroup type cgroup2 (rw)
debugfs on /sys/kernel/debug type debugfs (rw)
fusectl on /sys/fs/fuse/connections type fusectl (rw)""",
                {
                    "/proc": {"type": "virtual", "pseudo": True},
                    "/sys": {"type": "virtual", "pseudo": True},
                    "/dev/pts": {"type": "virtual", "pseudo": True},
                    "/run": {"type": "virtual", "pseudo": False},  # tmpfs
                    "/sys/fs/cgroup": {"type": "virtual", "pseudo": True},
                    "/sys/kernel/debug": {"type": "virtual", "pseudo": True},
                    "/sys/fs/fuse/connections": {"type": "virtual", "pseudo": True},
                },
            ),
            # Docker container with overlay and bind mounts
            (
                """overlay on / type overlay (rw,relatime,lowerdir=/var/lib/docker/overlay2/l/A:/var/lib/docker/overlay2/l/B,upperdir=/var/lib/docker/overlay2/c/diff,workdir=/var/lib/docker/overlay2/c/work)
/dev/vda1 on /etc/resolv.conf type ext4 (rw,relatime,bind)
/dev/vda1 on /etc/hostname type ext4 (rw,relatime,bind)
/dev/vda1 on /etc/hosts type ext4 (rw,relatime,bind)""",
                {
                    "/": {"type": "overlay", "filesystem": "overlay"},
                    "/etc/resolv.conf": {"type": "overlay", "filesystem": "ext4"},
                    "/etc/hostname": {"type": "overlay", "filesystem": "ext4"},
                    "/etc/hosts": {"type": "overlay", "filesystem": "ext4"},
                },
            ),
        ],
    )
    def test_multiple_mounts(
        self,
        filter_module: FilterModule,
        mount_output: str,
        expected_mounts: Dict[str, Dict[str, Any]],
    ) -> None:
        """Test parsing multiple mounts with correct classification."""
        facts = filter_module.mount(mount_output, facts=True)

        for mount_point, expected in expected_mounts.items():
            assert mount_point in facts["mounts"]
            mount = facts["mounts"][mount_point]
            for key, value in expected.items():
                assert mount[key] == value

    @pytest.mark.parametrize(
        "input_data,input_type",
        [
            # Command result dict
            (
                {
                    "stdout": "/dev/sda1 on / type ext4 (rw)",
                    "stdout_lines": ["/dev/sda1 on / type ext4 (rw)"],
                    "stderr": "",
                    "rc": 0,
                },
                "dict",
            ),
            # List of lines
            (
                [
                    "/dev/sda1 on / type ext4 (rw)",
                    "tmpfs on /tmp type tmpfs (rw)",
                ],
                "list",
            ),
            # Plain string
            (
                "/dev/sda1 on / type ext4 (rw)\ntmpfs on /tmp type tmpfs (rw)",
                "str",
            ),
        ],
    )
    def test_input_types(
        self,
        filter_module: FilterModule,
        input_data: Any,
        input_type: str,
    ) -> None:
        """Test mount filter with different input types."""
        result = filter_module.mount(input_data)

        # All should parse successfully
        assert len(result) >= 1
        assert result[0]["mount_point"] == "/"

        if input_type in ["list", "str"]:
            assert len(result) == 2
            assert result[1]["mount_point"] == "/tmp"

    def test_empty_input(self, filter_module: FilterModule) -> None:
        """Test handling of empty input."""
        # Empty string
        assert filter_module.mount("") == []
        assert filter_module.mount("", facts=True) == {"mounts": {}}

        # Empty list
        assert filter_module.mount([]) == []
        assert filter_module.mount([], facts=True) == {"mounts": {}}

    @pytest.mark.parametrize(
        "filesystem,expected_type,is_fuse",
        [
            # Standard filesystems
            ("ext4", "device", False),
            ("xfs", "device", False),
            ("btrfs", "device", False),
            ("zfs", "device", False),
            ("apfs", "device", False),
            # Virtual filesystems
            ("tmpfs", "virtual", False),
            ("ramfs", "virtual", False),
            # Pseudo filesystems
            ("proc", "virtual", False),  # pseudo=True would also be set
            ("sysfs", "virtual", False),  # pseudo=True would also be set
            ("devfs", "virtual", False),  # pseudo=True would also be set
            # Network filesystems
            ("nfs", "network", False),
            ("cifs", "network", False),
            ("smbfs", "network", False),
            # Overlay filesystems
            ("overlay", "overlay", False),
            ("overlayfs", "overlay", False),
            ("aufs", "overlay", False),
            # FUSE filesystems
            ("fuse.sshfs", "network", True),  # sshfs is network
            ("fuse.encfs", None, True),  # encfs has no specific type
            ("fuse.bindfs", "overlay", True),  # bindfs is overlay
        ],
    )
    def test_filesystem_classification(
        self,
        filter_module: FilterModule,
        filesystem: str,
        expected_type: str,
        is_fuse: bool,
    ) -> None:
        """Test correct classification of filesystem types."""
        # Create minimal mount output
        if filesystem.startswith("fuse."):
            mount_output = f"source on /mnt type {filesystem} (rw)"
        else:
            mount_output = f"/dev/sda1 on /mnt type {filesystem} (rw)"

        facts = filter_module.mount(mount_output, facts=True)

        if "/mnt" in facts["mounts"]:
            mount = facts["mounts"]["/mnt"]
            if expected_type:
                assert mount.get("type") == expected_type
            assert mount.get("fuse", False) == is_fuse