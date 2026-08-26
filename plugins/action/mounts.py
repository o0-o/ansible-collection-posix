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
    MOUNT_FILTER_DEFAULTS,
    PosixActionBase,
    compose_mounts,
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
        self._def_inventory_hostname(task_vars)

        result = super().run(tmp, task_vars=task_vars)
        del tmp  # unused

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
        """Get the mounts fact, keyed by mount point.

        The composition is shared with the facts module, which
        publishes the same shape under ``o0_storage.mounts``; this
        module only chooses which filesystem categories to report.

        :param task_vars: Task variables dictionary
        :returns: Dict of mount entries keyed by mountpoint
        """
        df_list = self._get_df_list(task_vars)
        mount_list = self._get_mount_list(task_vars)

        mounts, notes = compose_mounts(
            df_list,
            mount_list,
            filters={
                name: self._task.args.get(name, default)
                for name, default in MOUNT_FILTER_DEFAULTS.items()
            },
        )

        for note in notes:
            self._display.vvv(note)

        return mounts

    def _get_df_list(self, task_vars: dict[str, Any]) -> list[dict[str, Any]]:
        """Get df output as a list.

        :param task_vars: Task variables dictionary
        :returns: List of df entries
        :raises AnsibleActionFail: If df command fails
        """
        try:
            # Execute df command
            df_result = self._command(
                "df -P", task_vars=task_vars, check_mode=False
            )

            # Parse using df filter from module_utils
            return df(df_result)

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
            mount_result = self._command(
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
            cat_result = self._command(
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
