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

from typing import Any, Dict, List, Union

from ansible_collections.o0_o.posix.plugins.filter_utils import JCBase

DOCUMENTATION = r"""
---
name: mount
short_description: Parse mount command output
version_added: "1.1.0"
description:
  - Parse output from the mount command into structured data using jc
  - Can return either raw jc format or simplified facts structure
  - When used with facts=True, returns mount information organized by
    mount point
options:
  _input:
    description:
      - Command output from 'mount' as string, list of lines, or
        command result dict
    type: raw
    required: true
  facts:
    description:
      - If True, format output for direct merge into Ansible facts
      - Returns simplified structure with mounts organized by mount point
    type: bool
    default: false
requirements:
  - jc (Python library)
notes:
  - The jc library parses mount output into structured data
  - When facts=True, mount information is keyed by mount point for
    easy lookup
author:
  - oØ.o (@o0-o)
"""

EXAMPLES = r"""
# Parse mount output
- name: Get mount information
  ansible.builtin.command:
    cmd: mount
  register: mount_result

- name: Parse mount output
  ansible.builtin.debug:
    msg: "{{ mount_result.stdout | o0_o.posix.mount }}"

# Use facts format for simplified structure
- name: Parse for facts
  ansible.builtin.set_fact:
    mount_info: "{{ mount_result.stdout | o0_o.posix.mount(facts=true) }}"

- name: Display root filesystem info
  ansible.builtin.debug:
    msg: "Root mounted from {{ mount_info.mounts['/'].source }}"
"""

RETURN = r"""
# When facts=False (default)
_value:
  description: List of mount entries
  type: list
  elements: dict
  returned: always
  contains:
    filesystem:
      description: Source device or filesystem
      type: str
      sample: /dev/sda1
    mount_point:
      description: Directory where filesystem is mounted
      type: str
      sample: /home
    type:
      description: Filesystem type
      type: str
      sample: ext4
    options:
      description: Mount options
      type: list
      elements: str
      sample: ["rw", "relatime", "errors=remount-ro"]

# When facts=True
mounts:
  description: Mount information keyed by mount point
  type: dict
  returned: always
  contains:
    <mount_point>:
      description: Mount point information
      type: dict
      contains:
        source:
          description: Mount source when different from filesystem type
          type: str
          required: false
          sample: /dev/sda1
        type:
          description: Mount type classification
          type: str
          choices:
            - device
            - network
            - virtual
            - overlay
          sample: device
        filesystem:
          description: Filesystem type
          type: str
          sample: ext4
        pseudo:
          description: >-
            Whether this is a pseudo filesystem (kernel interface).
            Always present when type=virtual, true only for pseudo filesystems
          type: bool
          required: false
          sample: true
        fuse:
          description: Whether this is a FUSE filesystem
          type: bool
          sample: false
        options:
          description: Mount options as dictionary
          type: dict
          sample: {"rw": true, "relatime": true, "errors": "remount-ro"}
"""


class FilterModule(JCBase):
    """Filter for parsing mount command output using jc."""

    def filters(self) -> Dict[str, Any]:
        """Return the filter functions."""
        return {
            "mount": self.mount,
        }

    def _format_as_facts(self, parsed: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Format parsed mount data for Ansible facts structure.

        Converts jc's raw mount parsing into a simplified facts
        structure suitable for direct merge into Ansible facts, with
        mounts organized by mount point for easy lookup.

        :param parsed: Parsed mount data from jc
        :returns: Facts structure with mounts by mount point
        """
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

        # Overlay filesystems (views/unions/transforms of other
        # filesystems)
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
            "nsfs",
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
        }

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
            source = entry.get("filesystem", None)
            if source:
                source = source.lower()

            # Determine filesystem type
            filesystem = None
            options = entry.get("options", []).copy()
            if "type" in entry:
                # Use explicit type field if available
                filesystem = entry["type"]
            elif options:
                # On macOS and FreeBSD, type is the first option
                filesystem = options.pop(0)

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
            if filesystem in VIRTUAL_FS_TYPES or filesystem in PSEUDO_FS_TYPES:
                mount_info["type"] = "virtual"
                mount_info["source"] = None
                mount_info["pseudo"] = filesystem in PSEUDO_FS_TYPES
            elif filesystem in OVERLAY_FS_TYPES:
                mount_info["type"] = "overlay"
            elif filesystem in NETWORK_FS_TYPES:
                mount_info["type"] = "network"
            elif filesystem in DEVICE_FS_TYPES:
                mount_info["type"] = "device"

            # Determine mount type based on source
            elif source:
                if (
                    source.startswith(
                        ("/dev/", "uuid=", "label=", "partuuid=", "partlabel=")
                    )
                    and source != "/dev/fuse"
                ):
                    mount_info["type"] = "device"
                elif ":" in source or source.startswith("//"):
                    # Network filesystem (NFS, CIFS/SMB)
                    mount_info["type"] = "network"

            # Detect FUSE filesystems
            # Known FUSE filesystems without "fuse" prefix
            known_fuse_fs = {
                "bindfs",
                "encfs",
                "gocryptfs",
                "cryfs",
                "mergerfs",
                "lxcfs",
                "sshfs",
            }
            if filesystem:
                if (
                    # fuse, fuse.*, fuseblk but not fusectl
                    (filesystem.startswith("fuse") and filesystem != "fusectl")
                    or filesystem.endswith("-fuse")  # *-fuse variants
                    or filesystem.lower()
                    in known_fuse_fs  # Known FUSE filesystems
                ):
                    mount_info["fuse"] = True

            mounts[mount_point] = mount_info

        return {"mounts": mounts}

    def mount(
        self,
        data: Union[str, List[str], Dict[str, Any]],
        facts: bool = False,
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """Parse mount output into structured data using jc.

        :param data: Command output from 'mount'
        :param facts: If True, format for direct merge into Ansible
            facts
        :returns: Parsed mount data, or facts structure with mounts by
            mount point
        """
        # Get parsed data from jc
        parsed = self.parse_command(data, "mount")

        if not facts:
            # Return jc's parsed format directly
            return parsed

        # Format for facts module using separate method
        return self._format_as_facts(parsed)
