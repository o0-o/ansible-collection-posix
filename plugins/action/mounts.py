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

from typing import Any, Optional

from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase
from ansible_collections.o0_o.posix.plugins.module_utils import (
    PosixActionBase,
    df,
    mount,
    parse_fstab,
)


class ActionModule(PosixActionBase, ActionBase):
    """
    Gather mount point information from the target system.

    This action plugin gathers filesystem mount information by
    combining data from the 'df' and 'mount' commands. It returns
    a dictionary keyed by mount points with consolidated information.
    """

    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False
    _supports_diff = False

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Main entry point for the action plugin.

        Gathers mount point information from the target system using
        df and mount commands, then combines them into a comprehensive
        dictionary keyed by mount points.

        :param Optional[str] tmp: Temporary directory path (unused
            in modern Ansible)
        :param Optional[dict[str, Any]] task_vars: Task variables
            dictionary
        :returns dict[str, Any]: Dictionary with mount point
            information keyed by mount path
        """
        task_vars = task_vars or {}
        tmp = None  # unused in modern Ansible

        result = super().run(tmp, task_vars)

        # Validate module arguments
        argument_spec = {
            "device": {
                "type": "bool",
                "default": True,
            },
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
            "overlay": {
                "type": "bool",
                "default": True,
            },
            "fuse": {
                "type": "bool",
                "default": True,
            },
        }

        validation_result, new_module_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )

        self._task.args.update(new_module_args)

        try:
            # Get mount information as a dict keyed by mountpoint
            mounts_dict = self._get_mounts_dict(task_vars)

            # Get fstab information
            fstab_list = self._get_fstab_list(task_vars)

            result.update(
                {
                    "changed": False,
                    "mounts": mounts_dict,
                    "fstab": fstab_list,
                }
            )
        except Exception as e:
            self._display.vvv(f"Error getting mounts: {type(e).__name__}: {e}")
            raise AnsibleActionFail(f"Failed to get mount information: {e}")

        return result

    def _get_mounts_dict(
        self, task_vars: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        """Get mount information as a dict keyed by mountpoint.

        This method:
        1. Runs df and filters it, converting to dict with mountpoint
           keys
        2. Runs mount and filters it
        3. Merges mount entries into the df dict
        4. Only includes mount entries that have keys from the df dict

        :param task_vars: Task variables dictionary
        :returns: Dict of mount entries keyed by mountpoint
        """
        # Step 1: Get df output and convert to dict with mountpoint keys
        df_dict = self._get_df_dict(task_vars)

        # Step 2: Get mount output
        mount_list = self._get_mount_list(task_vars)

        # Step 3: Merge mount data into df dict
        # Only process mount entries that match df entries
        for mount_entry in mount_list:
            mountpoint = mount_entry.get("mount")
            if not mountpoint:
                continue

            # Only merge if this mountpoint exists in df output
            if mountpoint in df_dict:
                df_entry = df_dict[mountpoint]

                # Check if sources match
                df_source = df_entry.get("source")
                mount_source = mount_entry.get("source")

                # Merge mount data into df entry
                # Mount provides type and options that df doesn't have
                if "type" in mount_entry:
                    df_entry["type"] = mount_entry["type"]
                if "options" in mount_entry:
                    df_entry["options"] = mount_entry["options"]

                # If sources don't match, log it but still merge
                if df_source and mount_source and df_source != mount_source:
                    self._display.vvv(
                        f"Mount point {mountpoint}: df reports source as "
                        f"'{df_source}' but mount reports '{mount_source}'. "
                        f"Using df source."
                    )

        # Step 4: Filter the final dict based on module arguments
        filtered_dict = self._filter_mounts_dict(df_dict)

        return filtered_dict

    def _get_df_dict(
        self, task_vars: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        """Get df output and convert to dict keyed by mountpoint.

        :param task_vars: Task variables dictionary
        :returns: Dict of df entries keyed by mountpoint
        :raises AnsibleActionFail: If df command fails
        """
        try:
            # Execute df command
            df_result = self._cmd(
                "df -P", task_vars=task_vars, check_mode=False
            )

            # Parse using df filter from module_utils
            df_list = df(df_result)

            # Convert to dict keyed by mountpoint
            df_dict = {}
            for entry in df_list:
                mountpoint = entry.get("mount")
                if mountpoint:
                    # Remove the redundant 'mount' key since mountpoint
                    # is the dict key
                    entry.pop("mount", None)
                    df_dict[mountpoint] = entry

            return df_dict

        except Exception as e:
            raise AnsibleActionFail(f"Failed to execute df command: {e}")

    def _get_mount_list(
        self, task_vars: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Get mount output as a list.

        :param task_vars: Task variables dictionary
        :returns: List of mount entries
        :raises AnsibleActionFail: If mount command fails
        """
        try:
            # Execute mount command
            mount_result = self._cmd(
                "mount", task_vars=task_vars, check_mode=False
            )

            # Parse using mount filter from module_utils
            mount_list = mount(mount_result)

            return mount_list

        except Exception as e:
            raise AnsibleActionFail(f"Failed to execute mount command: {e}")

    def _get_fstab_list(
        self, task_vars: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Get fstab content as a list of parsed entries.

        :param task_vars: Task variables dictionary
        :returns: List of fstab entries
        """
        try:
            # Read /etc/fstab
            cat_result = self._cmd(
                "cat /etc/fstab", task_vars=task_vars, check_mode=False
            )

            # Extract content from command result
            if isinstance(cat_result, dict):
                content = cat_result.get("stdout", "")
            else:
                content = str(cat_result)

            # Parse using fstab_utils
            fstab_list = parse_fstab(content)

            return fstab_list

        except Exception as e:
            # If fstab cannot be read, return empty list
            # (not all systems have /etc/fstab)
            self._display.vvv(
                f"Could not read /etc/fstab: {type(e).__name__}: {e}"
            )
            return []

    def _should_include_mount(self, mount_info: dict[str, Any]) -> bool:
        """Check if mount should be included based on filter arguments.

        :param mount_info: Mount entry to check
        :returns: True if the mount should be included
        """
        include_device = self._task.args.get("device", True)
        include_virtual = self._task.args.get("virtual", False)
        include_network = self._task.args.get("network", True)
        include_pseudo = self._task.args.get("pseudo", None)
        include_overlay = self._task.args.get("overlay", True)
        include_fuse = self._task.args.get("fuse", True)

        # Default pseudo to virtual if not specified
        if include_pseudo is None:
            include_pseudo = include_virtual

        fs_type = mount_info.get("type", "")

        # Categorize filesystem types
        virtual_types = {
            "tmpfs",
            "devtmpfs",
            "proc",
            "sysfs",
            "devpts",
            "securityfs",
            "cgroup",
            "cgroup2",
            "debugfs",
            "tracefs",
            "configfs",
            "fusectl",
            "pstore",
            "efivarfs",
            "bpf",
            "autofs",
            "mqueue",
            "hugetlbfs",
            "rpc_pipefs",
            "binfmt_misc",
            "ramfs",
        }

        network_types = {
            "nfs",
            "nfs4",
            "cifs",
            "smb",
            "smbfs",
            "ncpfs",
            "ncp",
            "afs",
            "coda",
            "ftpfs",
            "sshfs",
            "webdav",
            "davfs",
        }

        overlay_types = {"overlay", "overlayfs", "aufs", "unionfs"}

        # Pseudo filesystems (subset of virtual)
        pseudo_types = {
            "proc",
            "sysfs",
            "devpts",
            "devtmpfs",
            "securityfs",
            "debugfs",
            "tracefs",
            "configfs",
            "fusectl",
            "pstore",
            "efivarfs",
            "bpf",
            "cgroup",
            "cgroup2",
            "mqueue",
            "hugetlbfs",
            "rpc_pipefs",
        }

        # Check filesystem type categories
        is_virtual = fs_type in virtual_types
        is_network = fs_type in network_types
        is_overlay = fs_type in overlay_types
        is_pseudo = fs_type in pseudo_types
        is_fuse = fs_type.startswith("fuse")

        # Device filesystems are those not in any special category
        is_device = not (is_virtual or is_network or is_overlay or is_fuse)

        # Apply filters
        if not include_device and is_device:
            return False
        if not include_virtual and is_virtual:
            return False
        if not include_network and is_network:
            return False
        if not include_overlay and is_overlay:
            return False
        if not include_pseudo and is_pseudo:
            return False
        if not include_fuse and is_fuse:
            return False

        return True

    def _filter_mounts_dict(
        self, mounts_dict: dict[str, dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """Filter mounts dict based on module arguments.

        :param mounts_dict: Dict of all mounts keyed by mountpoint
        :returns: Filtered dict of mounts
        """
        filtered = {}
        for mountpoint, mount_info in mounts_dict.items():
            if self._should_include_mount(mount_info):
                filtered[mountpoint] = mount_info

        return filtered
