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

from typing import Any, Dict, Optional, Set

from ansible.errors import AnsibleActionFail
from ansible_collections.o0_o.posix.plugins.action_utils.posix_base import (
    PosixBase,
)
from ansible_collections.o0_o.posix.plugins.filter import (
    DfFilter,
    MountFilter,
)


class ActionModule(PosixBase):
    """
    Gather mount point information from the target system.

    This action plugin gathers filesystem mount information by
    combining data from the 'mount' and 'df -P' commands. It returns
    a dictionary of mount points with device, filesystem type, and
    capacity information.
    """

    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False
    _supports_diff = False

    # Virtual filesystems to exclude by default
    VIRTUAL_FS_TYPES: Set[str] = {
        "autofs",
        "binfmt_misc",
        "bpf",
        "cgroup",
        "cgroup2",
        "configfs",
        "debugfs",
        "devfs",
        "devpts",
        "devtmpfs",
        "efivarfs",
        "fdescfs",
        "fusectl",
        "hugetlbfs",
        "mqueue",
        "nfsd",
        "overlay",
        "proc",
        "procfs",
        "pstore",
        "rpc_pipefs",
        "securityfs",
        "selinuxfs",
        "sysfs",
        "tmpfs",
        "tracefs",
        "vboxsf",
        "vmhgfs",
    }

    # Network filesystems
    NETWORK_FS_TYPES: Set[str] = {
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

    # Pseudo filesystems (subset of virtual, specifically for
    # kernel interfaces)
    PSEUDO_FS_TYPES: Set[str] = {
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
        "fusectl",
        "binfmt_misc",
    }

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point for the action plugin.

        Gathers mount point information from the target system using
        mount and df commands, then combines them into a comprehensive
        dictionary of filesystem information.

        :param Optional[str] tmp: Temporary directory path (unused
            in modern Ansible)
        :param Optional[Dict[str, Any]] task_vars: Task variables
            dictionary
        :returns Dict[str, Any]: Dictionary with mount point
            information

        .. note::
           The module uses the mount filter to parse both mount and
           df output, providing a unified view of filesystem mounts.
        """
        task_vars = task_vars or {}
        tmp = None  # unused in modern Ansible

        result = super().run(tmp, task_vars)

        # Validate module arguments
        argument_spec = {
            "virtual": {
                "type": "bool",
                "default": False,
            },
            "network": {
                "type": "bool",
                "default": True,
            },
            "pseudo": {
                "type": "bool",
                "default": None,  # Will default to virtual
            },
        }

        validation_result, new_module_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )

        self._task.args.update(new_module_args)

        # Get mount information
        try:
            mount_result = self._cmd(
                "mount", task_vars=task_vars, check_mode=False
            )
        except Exception as e:
            raise AnsibleActionFail(f"Failed to execute mount command: {e}")

        # Get df information for capacity data
        df_result = None
        try:
            df_result = self._cmd(
                "df -P", task_vars=task_vars, check_mode=False
            )
        except Exception as e:
            # df might not be available, continue without capacity info
            self._display.vvv(
                f"Failed to get df data (continuing without "
                f"capacity info): {e}"
            )

        # Parse mount data using facts mode
        mount_filter = MountFilter().filters()["mount"]
        include_virtual = self._task.args.get("virtual", False)
        include_network = self._task.args.get("network", True)
        include_pseudo = self._task.args.get("pseudo", None)

        # Default pseudo to virtual if not specified
        if include_pseudo is None:
            include_pseudo = include_virtual

        # Get mounts from mount command with facts mode
        mount_facts = mount_filter(mount_result, facts=True)
        mounts = mount_facts.get("mounts", {})

        # Filter out unwanted filesystem types
        filtered_mounts = {}
        for mount_point, mount_info in mounts.items():
            fs_type = mount_info.get("filesystem", "")

            # Skip filesystems based on type filters
            if not include_virtual and self._is_virtual_filesystem(fs_type):
                continue
            if not include_network and self._is_network_filesystem(fs_type):
                continue
            if not include_pseudo and self._is_pseudo_filesystem(fs_type):
                continue

            # Keep this mount
            filtered_mounts[mount_point] = mount_info

        # Parse df data if available using facts mode
        if df_result and df_result.get("rc") == 0:
            df_filter = DfFilter().filters()["df"]
            # Use facts mode to get the new structure with capacity
            df_facts = df_filter(df_result, facts=True)

            # Merge capacity info from df into mount data
            df_mounts = df_facts.get("mounts", {})
            for mount_point in filtered_mounts:
                if mount_point in df_mounts:
                    df_info = df_mounts[mount_point]
                    if "capacity" in df_info:
                        filtered_mounts[mount_point]["capacity"] = df_info[
                            "capacity"
                        ]

        # Sort by mount point for consistent output
        sorted_mounts = {
            k: filtered_mounts[k] for k in sorted(filtered_mounts.keys())
        }

        result.update(
            {
                "changed": False,
                "mounts": sorted_mounts,
            }
        )

        return result

    def _is_virtual_filesystem(self, fs_type: str) -> bool:
        """Check if a filesystem type is virtual.

        :param fs_type: Filesystem type string
        :returns: True if virtual, False otherwise
        """
        return fs_type in self.VIRTUAL_FS_TYPES

    def _is_network_filesystem(self, fs_type: str) -> bool:
        """Check if a filesystem type is network-based.

        :param fs_type: Filesystem type string
        :returns: True if network filesystem, False otherwise
        """
        return fs_type in self.NETWORK_FS_TYPES

    def _is_pseudo_filesystem(self, fs_type: str) -> bool:
        """Check if a filesystem type is a pseudo filesystem.

        :param fs_type: Filesystem type string
        :returns: True if pseudo filesystem, False otherwise
        """
        return fs_type in self.PSEUDO_FS_TYPES
