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

from typing import Any, Dict, Optional

from ansible.errors import AnsibleActionFail
from ansible_collections.o0_o.posix.plugins.action_utils import (
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

        # Get mount information
        mounts = self._get_mounts(task_vars)

        result.update(
            {
                "changed": False,
                "mounts": mounts,
            }
        )

        return result

    def _get_mounts(self, task_vars: Dict[str, Any]) -> Dict[str, Any]:
        """Get mount information from the system.

        :param task_vars: Task variables dictionary
        :returns: Dictionary of mount points with their information
        :raises AnsibleActionFail: If mount command fails
        """
        # Get raw mount output
        mount_result = self._get_mount_output(task_vars)

        # Get raw df output (optional)
        df_result = self._get_df_output(task_vars)

        # Parse mount data
        mounts = self._parse_mount_data(mount_result)

        # Filter mounts based on arguments
        filtered_mounts = self._filter_mounts(mounts)

        # Enhance with df data if available
        if df_result and df_result.get("rc") == 0:
            self._enhance_with_df_data(filtered_mounts, df_result)

        return filtered_mounts

    def _get_mount_output(self, task_vars: Dict[str, Any]) -> Dict[str, Any]:
        """Execute mount command and return result.

        :param task_vars: Task variables dictionary
        :returns: Command result dictionary
        :raises AnsibleActionFail: If mount command fails
        """
        try:
            return self._cmd("mount", task_vars=task_vars, check_mode=False)
        except Exception as e:
            raise AnsibleActionFail(f"Failed to execute mount command: {e}")

    def _get_df_output(
        self, task_vars: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Execute df command and return result.

        :param task_vars: Task variables dictionary
        :returns: Command result dictionary or None if failed
        """
        try:
            return self._cmd("df -P", task_vars=task_vars, check_mode=False)
        except Exception as e:
            # df might not be available, continue without capacity info
            self._display.vvv(
                f"Failed to get df data (continuing without "
                f"capacity info): {e}"
            )
            return None

    def _parse_mount_data(
        self, mount_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Parse mount command output using mount filter.

        :param mount_result: Result from mount command
        :returns: Parsed mount information dictionary
        """
        mount_filter = MountFilter().filters()["mount"]
        mount_facts = mount_filter(mount_result, facts=True)
        return mount_facts.get("mounts", {})

    def _filter_mounts(self, mounts: Dict[str, Any]) -> Dict[str, Any]:
        """Filter mounts based on module arguments.

        :param mounts: Dictionary of all mounts
        :returns: Filtered dictionary of mounts
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

        # Filter out unwanted mount types
        filtered_mounts = {}
        for mount_point, mount_info in mounts.items():
            mount_type = mount_info.get("type")
            is_fuse = mount_info.get("fuse", False)
            is_pseudo = mount_info.get("pseudo", False)

            # Skip mounts based on type filters
            if not include_device and mount_type == "device":
                continue
            if not include_virtual and mount_type == "virtual":
                continue
            if not include_network and mount_type == "network":
                continue
            if not include_overlay and mount_type == "overlay":
                continue

            # Filter by pseudo status (subset of virtual)
            if not include_pseudo and mount_type == "virtual" and is_pseudo:
                continue

            # Filter by FUSE status
            if not include_fuse and is_fuse:
                continue

            # Keep this mount
            filtered_mounts[mount_point] = mount_info

        return filtered_mounts

    def _enhance_with_df_data(
        self, mounts: Dict[str, Any], df_result: Dict[str, Any]
    ) -> None:
        """Enhance mount data with capacity info from df.

        :param mounts: Dictionary of mounts to enhance
        :param df_result: Result from df command
        """
        df_filter = DfFilter().filters()["df"]
        # Use facts mode to get the new structure with capacity
        df_facts = df_filter(df_result, facts=True)

        # Merge capacity info from df into mount data
        df_mounts = df_facts.get("mounts", {})
        for mount_point in mounts:
            if mount_point in df_mounts:
                df_info = df_mounts[mount_point]
                if "capacity" in df_info:
                    mounts[mount_point]["capacity"] = df_info["capacity"]
