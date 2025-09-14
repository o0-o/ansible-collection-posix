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

from typing import Any, Dict, List, Optional

from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase
from ansible_collections.o0_o.posix.plugins.module_utils import (
    PosixActionBase,
)
from ansible_collections.o0_o.posix.plugins.filter import (
    DfFilter,
    MountFilter,
)


class ActionModule(PosixActionBase, ActionBase):
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

    def _get_mounts(self, task_vars: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get mount information from the system.

        :param task_vars: Task variables dictionary
        :returns: List of mount entries with their information
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
    ) -> List[Dict[str, Any]]:
        """Parse mount command output using mount filter.

        :param mount_result: Result from mount command
        :returns: List of parsed mount entries
        """
        mount_filter = MountFilter().filters()["mount"]
        # mount filter now returns a list directly when facts=True
        return mount_filter(mount_result, facts=True)

    def _should_include_mount(self, mount_info: Dict[str, Any]) -> bool:
        """Check if a mount should be included based on filter arguments.

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

        mount_type = mount_info.get("type")
        is_fuse = mount_info.get("fuse", False)
        # Pseudo filesystems have source="kernel"
        is_pseudo = mount_info.get("source") == "kernel"

        # Skip mounts based on type filters
        if not include_device and mount_type == "regular":
            return False
        if not include_virtual and mount_type == "virtual":
            return False
        if not include_network and mount_type == "network":
            return False
        if not include_overlay and mount_type == "overlay":
            return False

        # Filter by pseudo status (subset of virtual)
        if not include_pseudo and mount_type == "virtual" and is_pseudo:
            return False

        # Filter by FUSE status
        if not include_fuse and is_fuse:
            return False

        return True

    def _filter_mounts(self, mounts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter mounts based on module arguments.

        :param mounts: List of all mounts
        :returns: Filtered list of mounts
        """
        # Filter out unwanted mount types
        filtered_mounts = []
        for mount_info in mounts:
            if self._should_include_mount(mount_info):
                filtered_mounts.append(mount_info)

        return filtered_mounts

    def _enhance_with_df_data(
        self, mounts: List[Dict[str, Any]], df_result: Dict[str, Any]
    ) -> None:
        """Enhance mount data with capacity info from df.

        Iterates through df entries and merges capacity data into matching
        mount entries (by source and target). Creates new entries for df
        entries that don't have a corresponding mount entry.

        :param mounts: List of mounts to enhance (modified in place)
        :param df_result: Result from df command
        """
        df_filter = DfFilter().filters()["df"]
        # df filter now returns a list directly when facts=True
        df_entries = df_filter(df_result, facts=True)

        # Track which df entries have been merged
        merged_df_indices = set()
        
        # First pass: merge capacity into existing mount entries
        for df_idx, df_entry in enumerate(df_entries):
            df_target = df_entry.get("target")
            df_source = df_entry.get("source")
            
            for mount_entry in mounts:
                mount_target = mount_entry.get("target")
                mount_source = mount_entry.get("source")
                
                # Match by both source and target for accuracy
                if df_target == mount_target:
                    # Check source compatibility
                    if df_source and mount_source and df_source != mount_source:
                        # Sources differ - check if it's just a symlink difference
                        # or device naming difference, but still merge capacity
                        self._display.vvv(
                            f"Mount point {mount_target}: df reports source as "
                            f"'{df_source}' but mount reports '{mount_source}'. "
                            f"Merging capacity data anyway."
                        )
                    
                    # Merge capacity info
                    if "capacity" in df_entry:
                        mount_entry["capacity"] = df_entry["capacity"]
                    
                    merged_df_indices.add(df_idx)
                    break
        
        # Second pass: add df entries that weren't in mount output
        # (This can happen for some filesystem types that df sees but mount doesn't)
        # BUT only if they pass the same filtering criteria
        for df_idx, df_entry in enumerate(df_entries):
            if df_idx not in merged_df_indices:
                # Check if this df-only entry should be included based on filters
                if self._should_include_mount(df_entry):
                    # This df entry didn't match any mount entry
                    # Add it as a new entry (it has capacity but might lack other mount details)
                    self._display.vvv(
                        f"Adding df-only entry for {df_entry.get('target', 'unknown')}"
                    )
                    mounts.append(df_entry)
