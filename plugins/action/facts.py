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
import time

from ansible.errors import AnsibleActionFail, AnsibleConnectionFailure
from ansible.plugins.action import ActionBase
from ansible_collections.o0_o.posix.plugins.module_utils import (
    PosixActionBase,
    uname,
    dmidecode,
    mount,
    fstab,
    parse_shells,
)


class ActionModule(PosixActionBase, ActionBase):
    """Gather comprehensive POSIX facts from the managed host.

    This action plugin collects system information using various
    module_utils functions including uname, dmidecode, mount, fstab,
    users/groups, locale, and timezone data.

    Facts are organized into logical namespaces: o0_os, o0_hardware,
    o0_storage, and o0_network.
    """

    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False
    _supports_diff = False

    # Define subset groups
    SUBSET_GROUPS = {
        "min": {"uname", "locale", "timezone", "compliance"},
        "all": {
            "uname",
            "locale",
            "timezone",
            "hardware",
            "compliance",
            "storage",
            "users",
        },
        "storage": {"mounts", "fstab"},
    }

    # Map individual subsets to gathering methods
    SUBSET_METHODS = {
        "uname": "_gather_uname",
        "locale": "_gather_locale",
        "timezone": "_gather_timezone",
        "hardware": "_gather_hardware",
        "compliance": "_gather_compliance",
        "mounts": "_gather_mounts",
        "fstab": "_gather_fstab",
        "users": "_gather_users",
    }

    def _gather_uname(
        self, task_vars: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Gather kernel, hostname, and architecture from uname.

        :param Optional[Dict[str, Any]] task_vars: Task variables
        :returns Dict[str, Any]: Uname facts
        """
        cmd_result = self._cmd(["uname", "-a"], task_vars=task_vars)
        uname_output = cmd_result.get("stdout", "")
        uname_facts = uname(uname_output)

        facts = {}

        # o0_os.kernel
        if "kernel" in uname_facts:
            facts.setdefault("o0_os", {})["kernel"] = uname_facts["kernel"]

        # o0_network.hostname
        if "hostname" in uname_facts:
            facts.setdefault("o0_network", {})["hostname"] = uname_facts[
                "hostname"
            ]

        # o0_hardware.baseboard.architecture (just the string)
        if "architecture" in uname_facts:
            facts.setdefault("o0_hardware", {}).setdefault("baseboard", {})[
                "architecture"
            ] = uname_facts["architecture"]

        return facts

    def _gather_locale(
        self, task_vars: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Gather locale information.

        :param Optional[Dict[str, Any]] task_vars: Task variables
        :returns Dict[str, Any]: Locale facts
        """
        # Use the locale action plugin logic
        cmd_result = self._cmd(["locale"], task_vars=task_vars)
        locale_output = cmd_result.get("stdout", "")

        # Parse locale output (key=value format)
        locale_facts = {}
        for line in locale_output.strip().split("\n"):
            if "=" in line:
                key, value = line.split("=", 1)
                # Remove quotes
                value = value.strip('"')
                if key == "LANG":
                    locale_facts["language"] = value
                elif key == "LC_ALL":
                    locale_facts["all"] = value
                # Store other LC_* variables
                elif key.startswith("LC_"):
                    locale_facts[key.lower()] = value

        return {"o0_os": {"locale": locale_facts}}

    def _gather_timezone(
        self, task_vars: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Gather time and timezone information.

        :param Optional[Dict[str, Any]] task_vars: Task variables
        :returns Dict[str, Any]: Time/timezone facts
        """
        # Get current time
        current_epoch = int(time.time())
        cmd_result = self._cmd(
            ["date", "+%Y-%m-%d %H:%M:%S %Z"], task_vars=task_vars
        )
        pretty_time = cmd_result.get("stdout", "").strip()

        # Get timezone info
        tz_cmd = self._cmd(["date", "+%Z %z"], task_vars=task_vars)
        tz_output = tz_cmd.get("stdout", "").strip()
        tz_parts = tz_output.split()
        tz_name = tz_parts[0] if tz_parts else ""
        tz_offset = tz_parts[1] if len(tz_parts) > 1 else ""

        time_facts = {
            "epoch": current_epoch,
            "pretty": pretty_time,
            "zone": {"name": tz_name, "offset": tz_offset},
        }

        # Get /etc/localtime symlink info
        localtime_result = self._execute_module(
            module_name="o0_o.posix.read",
            module_args={
                "path": "/etc/localtime",
                "metadata": False,
                "type": True,
                "links": True,
            },
            task_vars=task_vars,
        )

        if not localtime_result.get("failed") and localtime_result.get(
            "file", {}
        ).get("exists"):
            file_info = localtime_result["file"]
            localtime_info = {}

            file_type = file_info.get("type")
            if file_type:
                localtime_info["type"] = file_type
                # Include links only for symlinks
                if file_type == "link":
                    links = file_info.get("links")
                    if links:
                        localtime_info["links"] = links

            if localtime_info:
                time_facts["zone"]["config"] = {
                    "/etc/localtime": localtime_info
                }

        return {"o0_os": {"time": time_facts}}

    def _gather_hardware(
        self, task_vars: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Gather hardware information from dmidecode.

        :param Optional[Dict[str, Any]] task_vars: Task variables
        :returns Dict[str, Any]: Hardware facts
        """
        # Run dmidecode command
        cmd_result = self._cmd(
            ["dmidecode"], task_vars=task_vars, check_mode=False
        )

        if cmd_result.get("rc") != 0:
            raise AnsibleActionFail(
                f"dmidecode command failed: {cmd_result.get('stderr', '')}"
            )

        hardware = dmidecode(cmd_result.get("stdout", ""))

        # Map dmidecode output to o0_hardware namespace
        hw_facts = {}
        if "baseboard" in hardware:
            hw_facts["baseboard"] = hardware["baseboard"]
        if "processors" in hardware:
            hw_facts["processors"] = hardware["processors"]
        if "memory" in hardware:
            hw_facts["memory"] = hardware["memory"]
        if "chassis" in hardware:
            hw_facts["chassis"] = hardware["chassis"]
        if "power" in hardware:
            hw_facts["power"] = hardware["power"]

        return {"o0_hardware": hw_facts}

    def _gather_compliance(
        self, task_vars: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Gather POSIX/SUS compliance information.

        :param Optional[Dict[str, Any]] task_vars: Task variables
        :returns Dict[str, Any]: Compliance facts
        """
        # Execute the compliance action plugin
        compliance_result = self._execute_module(
            module_name="o0_o.posix.compliance",
            module_args={},
            task_vars=task_vars,
        )

        # Extract compliance data from result
        if compliance_result.get("failed"):
            return {}

        compliance_data = compliance_result.get("compliance", {})
        if not compliance_data:
            return {}

        return {"o0_os": {"compliance": compliance_data}}

    def _gather_mounts(
        self, task_vars: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Gather current mount points.

        :param Optional[Dict[str, Any]] task_vars: Task variables
        :returns Dict[str, Any]: Mount facts
        """
        cmd_result = self._cmd(["mount"], task_vars=task_vars)
        mount_output = cmd_result.get("stdout", "")
        mount_facts = mount(mount_output)

        return {"o0_storage": {"mounts": mount_facts}}

    def _gather_fstab(
        self, task_vars: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Gather /etc/fstab configuration.

        :param Optional[Dict[str, Any]] task_vars: Task variables
        :returns Dict[str, Any]: Fstab facts
        """
        slurp_result = self._execute_module(
            module_name="ansible.builtin.slurp",
            module_args={"src": "/etc/fstab"},
            task_vars=task_vars,
        )

        if slurp_result.get("failed"):
            # fstab might not exist or be readable
            return {}

        fstab_facts = fstab(slurp_result)

        return {"o0_storage": {"config": {"/etc/fstab": fstab_facts}}}

    def _gather_users(
        self, task_vars: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Gather user and group information.

        :param Optional[Dict[str, Any]] task_vars: Task variables
        :returns Dict[str, Any]: User/group facts
        """
        # Read /etc/passwd
        passwd_slurp = self._execute_module(
            module_name="ansible.builtin.slurp",
            module_args={"src": "/etc/passwd"},
            task_vars=task_vars,
        )

        # Read /etc/group
        group_slurp = self._execute_module(
            module_name="ansible.builtin.slurp",
            module_args={"src": "/etc/group"},
            task_vars=task_vars,
        )

        # Read /etc/shells
        shells_slurp = self._execute_module(
            module_name="ansible.builtin.slurp",
            module_args={"src": "/etc/shells"},
            task_vars=task_vars,
        )

        facts = {"o0_os": {}}

        # Parse users
        if not passwd_slurp.get("failed"):
            from ansible_collections.o0_o.posix.plugins.module_utils import (
                passwd_info,
            )

            users = passwd_info(passwd_slurp)
            facts["o0_os"]["users"] = users

        # Parse groups
        if not group_slurp.get("failed"):
            from ansible_collections.o0_o.posix.plugins.module_utils import (
                group_info,
            )

            groups = group_info(group_slurp)
            facts["o0_os"]["groups"] = groups

        # Parse shells
        if not shells_slurp.get("failed"):
            shells = parse_shells(shells_slurp)
            facts["o0_os"]["shells"] = shells

        return facts

    def _resolve_subsets(self, gather_subset: list) -> Set[str]:
        """Resolve gather_subset into individual subsets.

        :param list gather_subset: List of subset specifications
        :returns Set[str]: Set of individual subsets to gather
        """
        # Start with empty set if only exclusions, otherwise empty
        if all(s.startswith("!") for s in gather_subset):
            # All exclusions - start with all subsets
            selected = set(self.SUBSET_METHODS.keys())
        else:
            selected = set()

        for subset in gather_subset:
            if subset == "all":
                # Add all individual subsets
                selected.update(self.SUBSET_GROUPS["all"])
            elif subset == "min":
                # Add minimal subsets
                selected.update(self.SUBSET_GROUPS["min"])
            elif subset == "storage":
                # Add storage subsets
                selected.update(self.SUBSET_GROUPS["storage"])
            elif subset == "!all":
                # Remove all subsets
                selected.clear()
            elif subset.startswith("!"):
                # Remove specific subset
                selected.discard(subset[1:])
            elif subset in self.SUBSET_METHODS:
                # Add specific subset
                selected.add(subset)
            else:
                raise AnsibleActionFail(f"Invalid gather_subset: {subset}")

        return selected

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Main entry point for the action plugin.

        :param Optional[str] tmp: Temporary directory path
        :param Optional[Dict[str, Any]] task_vars: Task variables
        :returns Dict[str, Any]: Result dictionary with ansible_facts
        """
        task_vars = task_vars or {}
        tmp = None

        # Validate arguments
        argument_spec = {
            "gather_subset": {
                "type": "list",
                "elements": "str",
                "default": ["all"],
            }
        }

        validation_result, new_module_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )
        gather_subset = new_module_args["gather_subset"]

        result = super().run(tmp, task_vars)

        # Always check POSIX compliance first to validate the host
        try:
            compliance_facts = self._gather_compliance(task_vars=task_vars)
            from ansible_collections.o0_o.posix.plugins.module_utils import (
                is_posix as check_is_posix,
            )

            # Extract compliance dict from o0_os namespace
            compliance_dict = {}
            if "o0_os" in compliance_facts:
                compliance_dict = compliance_facts["o0_os"].get(
                    "compliance", {}
                )

            is_posix_compliant = check_is_posix(compliance_dict)

            # If definitely not POSIX, skip gathering facts
            if is_posix_compliant is False:
                result.update(
                    {
                        "skipped": True,
                        "skip_reason": (
                            "This does not appear to be a POSIX system."
                        ),
                        "ansible_facts": {},
                    }
                )
                return result
        except AnsibleConnectionFailure:
            raise
        except Exception as e:
            # If compliance check fails, log warning but continue
            host = self._get_inventory_hostname(task_vars)
            self._display.warning(
                f"[{host}] Failed to check POSIX compliance: {e}"
            )
            compliance_facts = {}

        # Resolve subsets
        selected_subsets = self._resolve_subsets(gather_subset)

        # Gather facts for each selected subset
        all_facts = {}

        # Include compliance facts if compliance is in selected subsets
        if "compliance" in selected_subsets and compliance_facts:
            for namespace, namespace_facts in compliance_facts.items():
                if namespace not in all_facts:
                    all_facts[namespace] = {}
                # Deep merge for nested dicts like config
                for key, value in namespace_facts.items():
                    if (
                        key in all_facts[namespace]
                        and isinstance(all_facts[namespace][key], dict)
                        and isinstance(value, dict)
                    ):
                        # Merge nested dicts
                        all_facts[namespace][key].update(value)
                    else:
                        all_facts[namespace][key] = value

        for subset in selected_subsets:
            # Skip compliance as it's already been gathered
            if subset == "compliance":
                continue

            if subset in self.SUBSET_METHODS:
                method_name = self.SUBSET_METHODS[subset]
                gather_method = getattr(self, method_name)

                try:
                    subset_facts = gather_method(task_vars=task_vars)

                    # Deep merge subset_facts into all_facts
                    for namespace, namespace_facts in subset_facts.items():
                        if namespace not in all_facts:
                            all_facts[namespace] = {}
                        # Deep merge for nested dicts like config
                        for key, value in namespace_facts.items():
                            if (
                                key in all_facts[namespace]
                                and isinstance(all_facts[namespace][key], dict)
                                and isinstance(value, dict)
                            ):
                                # Merge nested dicts
                                all_facts[namespace][key].update(value)
                            else:
                                all_facts[namespace][key] = value

                except AnsibleConnectionFailure:
                    raise
                except Exception as e:
                    host = self._get_inventory_hostname(task_vars)
                    self._display.warning(
                        f"[{host}] Failed to gather {subset} facts: {e}"
                    )

        # Special case: merge architecture into hardware.baseboard if
        # both uname and hardware were gathered
        if (
            "uname" in selected_subsets
            and "hardware" in selected_subsets
            and "o0_hardware" in all_facts
        ):
            # Architecture from uname is already in
            # o0_hardware.baseboard.architecture
            # If dmidecode also has baseboard, merge them
            pass  # Already handled in _gather_uname

        result.update({"ansible_facts": all_facts})

        return result
