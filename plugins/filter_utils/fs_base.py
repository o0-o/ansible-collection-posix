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

"""Base classes and utilities for filesystem-related filters."""

from __future__ import annotations

from typing import Any, Dict, List


class FilesystemBase:
    """Base class for filesystem classification and facts formatting."""

    # Device-backed filesystems
    DEVICE_FS_TYPES = {
        "ext2",
        "ext3",
        "ext4",
        "xfs",
        "btrfs",
        "zfs",
        "zfs_member",
        "apfs",
        "ufs",
        "ffs",
        "hfs",
        "hfsplus",
        "jfs",
        "reiserfs",
        "f2fs",
        "nilfs2",
        "ocfs2",
        "gfs2",
        "vfat",
        "msdos",
        "exfat",
        "ntfs",
        "ntfs3",
        "bcachefs",
        "iso9660",
        "udf",
        "squashfs",
        "erofs",
    }

    # Pseudo filesystems (kernel interfaces - subset of virtual)
    PSEUDO_FS_TYPES = {
        "proc",
        "procfs",
        "sysfs",
        "devfs",
        "devpts",
        "devtmpfs",
        "debugfs",
        "securityfs",
        "selinuxfs",
        "cgroup",
        "cgroup2",
        "pstore",
        "efivarfs",
        "configfs",
        "hugetlbfs",
        "mqueue",
        "bpf",
        "tracefs",
        "fusectl",  # Control interface for FUSE, not a FUSE filesystem
        "binfmt_misc",
        "rpc_pipefs",  # RPC kernel interface
        "nsfs",
    }

    # Virtual filesystems (memory-based, not kernel interfaces)
    VIRTUAL_FS_TYPES = {
        "tmpfs",
        "ramfs",  # RAM-based filesystem
        "autofs",
        "nfsd",
        "fdescfs",
        "vboxsf",
        "vmhgfs",
    }

    # Views/unions/transforms of other filesystems
    OVERLAY_FS_TYPES = {
        # Union / Merge filesystems
        "overlay",
        "overlayfs",
        "aufs",
        "unionfs",
        "unionfs-fuse",
        "fuse.unionfs",
        "mergerfs",
        "fuse.mergerfs",
        "mhddfs",
        "fuse.mhddfs",
        # Transform / Re-mapping filesystems
        "bindfs",
        "fuse.bindfs",
        "nullfs",
        "encfs",
        "fuse.encfs",
        "gocryptfs",
        "fuse.gocryptfs",
        "cryfs",
        "fuse.cryfs",
        "ecryptfs",
        "fusecompress",
        "fuse.fusecompress",
        "compfused",
        "fuse.compfused",
        # Isolation / Container-specific
        "lxcfs",
        "fuse.lxcfs",
        "shiftfs",
        # Snapshot / Copy-on-Write
        "translucentfs",
        "fuse.translucentfs",
    }

    # Network filesystems
    NETWORK_FS_TYPES = {
        "nfs",
        "nfs4",
        "smbfs",
        "cifs",
        "afs",
        "coda",
        "ncpfs",
        "sshfs",
        "fuse.sshfs",
        "glusterfs",
        "ceph",
        "9p",
        "smb3",
        "lustre",
        "orangefs",
        "pmxfs",
    }

    # Known FUSE filesystems without "fuse" prefix or "-fuse" suffix
    FUSE_FS_TYPES = {
        "bindfs",
        "encfs",
        "gocryptfs",
        "cryfs",
        "mergerfs",
        "lxcfs",
        "sshfs",
        "ntfs-3g",  # FUSE NTFS (kernel-backed is 'ntfs' or 'ntfs3')
        "osxfuse",  # macOS FUSE type name on some versions
        "osxfusefs",  # older macOS FUSE
        "macfuse",  # newer macOS FUSE
    }

    def format_mounts_as_facts(self, parsed: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Format parsed mount data for Ansible facts structure.

        Expects normalized mount data with standardized keys:
        - mount_point: str - The mount point path
        - source: str - The source device/filesystem (optional)
        - filesystem: str - The filesystem type
        - options: List[str] - Mount options

        Additional optional keys preserved:
        - dump: int - Dump frequency (from fstab)
        - pass: int - fsck pass number (from fstab)

        :param parsed: Normalized mount data
        :returns: Facts structure with mounts by mount point
        """
        mounts = {}

        for entry in parsed:
            # Keys should be set explicity to None if they are
            # definitively irrelevant or absent. Key should be excluded
            # entirely if their value is unknown or ambiguous.

            mount_point = entry.get("mount_point")
            if not mount_point:
                continue

            mount_info = {"fuse": False}

            # Get source
            source = entry.get("source")
            if isinstance(source, str) and source.lower() in ("-", "none"):
                source = None

            # Get filesystem type and options
            filesystem = entry.get("filesystem")

            # Handle swap entries - use "swap" as mount point if "none" is specified
            if mount_point.lower() == "none" and filesystem == "swap":
                mount_point = "swap"
            options = list(entry.get("options", []).copy())

            if filesystem:
                filesystem = filesystem.lower()

            if filesystem == "fuseblk":
                mount_info["type"] = "device"

            new_options = {}
            for opt in options:
                split_opt = opt.split("=", 1)
                # Check for FUSE subtype in options and use it if
                # filesystem is generic
                if (
                    filesystem in ("fuse", "fuseblk")
                    and split_opt[0] == "subtype"
                ):
                    # Extract subtype and use it as filesystem
                    filesystem = split_opt[1] if len(split_opt) > 1 else None
                    mount_info["fuse"] = True
                    # Don't add subtype to new_options
                else:
                    new_options[split_opt[0]] = (
                        split_opt[1] if len(split_opt) > 1 else True
                    )

            if filesystem not in (None, "fuse", "fuseblk"):
                mount_info["filesystem"] = filesystem

            # Only set source if it's different from filesystem
            # This avoids redundancy for virtual filesystems like
            # tmpfs, proc, etc.
            if source and source != filesystem:
                mount_info["source"] = source

            if new_options:
                mount_info["options"] = new_options

            # Determine mount type based on filesystem
            is_bind = mount_info.get("options", {}).get(
                "bind", False
            ) or mount_info.get("options", {}).get("rbind", False)
            if filesystem in self.VIRTUAL_FS_TYPES or filesystem in self.PSEUDO_FS_TYPES:
                mount_info["type"] = "virtual"
                mount_info["source"] = None
                mount_info["pseudo"] = filesystem in self.PSEUDO_FS_TYPES
            elif filesystem in self.OVERLAY_FS_TYPES or is_bind:
                mount_info["type"] = "overlay"
            elif filesystem in self.NETWORK_FS_TYPES:
                mount_info["type"] = "network"
            elif filesystem in self.DEVICE_FS_TYPES:
                mount_info["type"] = "device"

            # Determine mount type based on source
            elif source:
                if (
                    source.lower().startswith(
                        ("/dev/", "uuid=", "label=", "partuuid=", "partlabel=")
                    )
                    and source != "/dev/fuse"
                ):
                    mount_info["type"] = "device"
                elif (
                    ":" in source and not source.startswith("/")
                ) or source.startswith("//"):
                    # Network filesystem (NFS, CIFS/SMB)
                    mount_info["type"] = "network"

            # Detect FUSE filesystems
            if filesystem:
                if (
                    # fuse, fuse.*, fuseblk but not fusectl
                    (filesystem.startswith("fuse") and filesystem != "fusectl")
                    or filesystem.endswith("-fuse")  # *-fuse variants
                    or filesystem in self.FUSE_FS_TYPES  # Known FUSE filesystems
                ):
                    mount_info["fuse"] = True

            # Handle dump field if present (from fstab)
            if "dump" in entry:
                dump_value = entry["dump"]
                dump_dict = {}

                # Check if it's a valid integer
                if isinstance(dump_value, int):
                    if dump_value < 0:
                        dump_dict["invalid"] = dump_value
                    else:
                        dump_dict["enabled"] = dump_value > 0
                        if dump_value > 0:
                            dump_dict["days"] = dump_value
                else:
                    # Not an integer
                    dump_dict["invalid"] = dump_value

                mount_info["dump"] = dump_dict

            # Handle pass field if present (from fstab)
            if "pass" in entry:
                pass_value = entry["pass"]
                fsck_dict = {}

                # Check if it's a valid integer
                if isinstance(pass_value, int):
                    if pass_value < 0:
                        # Invalid but treat as disabled (common practice)
                        fsck_dict["invalid"] = pass_value
                        fsck_dict["enabled"] = False
                    else:
                        fsck_dict["enabled"] = pass_value > 0
                        if pass_value > 0:
                            fsck_dict["pass"] = pass_value
                else:
                    # Not an integer
                    fsck_dict["invalid"] = pass_value

                mount_info["fsck"] = fsck_dict

            mounts[mount_point] = mount_info

        return {"mounts": mounts}
