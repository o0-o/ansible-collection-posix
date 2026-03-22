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

import time
from typing import Any, Optional

from ansible.errors import AnsibleActionFail, AnsibleConnectionFailure
from ansible.plugins.action import ActionBase

from ansible_collections.o0_o.posix.plugins.module_utils import (
    PosixActionBase,
    dmidecode,
    fstab,
    mount,
    parse_shells,
    passwd_info,
    group_info,
)
from ansible_collections.o0_o.posix.plugins.module_utils.uname_utils import (
    _parse_uname,
)


class ActionModule(PosixActionBase, ActionBase):
    """Gather comprehensive POSIX facts from the managed host.

    Collects system information using shell commands and file reads,
    organized into logical namespaces: o0_os, o0_hardware,
    o0_storage, and o0_network.
    """

    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False
    _supports_diff = False

    # Subset groups
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
        self, task_vars: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Gather kernel, hostname, and architecture from uname.

        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns dict[str, Any]: Uname facts
        """
        cmd_result = self._command(["uname", "-a"], task_vars=task_vars)
        uname_output = cmd_result.get("stdout", "")
        parsed, errors = _parse_uname(uname_output, "[uname] ")

        if errors:
            for err in errors:
                self._display.warning(f"[{self.inventory_hostname}] {err}")
        if parsed is None:
            return {}

        facts = {}

        if "kernel" in parsed:
            facts.setdefault("o0_os", {})["kernel"] = parsed["kernel"]

        if "hostname" in parsed:
            facts.setdefault("o0_network", {})["hostname"] = parsed["hostname"]

        if "architecture" in parsed:
            facts.setdefault("o0_hardware", {}).setdefault("baseboard", {})[
                "architecture"
            ] = parsed["architecture"]

        return facts

    def _gather_locale(
        self, task_vars: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Gather locale information.

        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns dict[str, Any]: Locale facts
        """
        cmd_result = self._command(["locale"], task_vars=task_vars)
        locale_output = cmd_result.get("stdout", "")

        locale_facts = {}
        for line in locale_output.strip().split("\n"):
            if "=" in line:
                key, value = line.split("=", 1)
                value = value.strip('"')
                if key == "LANG":
                    locale_facts["language"] = value
                elif key == "LC_ALL":
                    locale_facts["all"] = value
                elif key.startswith("LC_"):
                    locale_facts[key.lower()] = value

        return {"o0_os": {"locale": locale_facts}}

    def _gather_timezone(
        self, task_vars: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Gather time and timezone information.

        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns dict[str, Any]: Time/timezone facts
        """
        current_epoch = int(time.time())
        cmd_result = self._command(
            ["date", "+%Y-%m-%d %H:%M:%S %Z"],
            task_vars=task_vars,
        )
        pretty_time = cmd_result.get("stdout", "").strip()

        tz_cmd = self._command(["date", "+%Z %z"], task_vars=task_vars)
        tz_output = tz_cmd.get("stdout", "").strip()
        tz_parts = tz_output.split()
        tz_name = tz_parts[0] if tz_parts else ""
        tz_offset = tz_parts[1] if len(tz_parts) > 1 else ""

        time_facts = {
            "epoch": current_epoch,
            "pretty": pretty_time,
            "zone": {"name": tz_name, "offset": tz_offset},
        }

        return {"o0_os": {"time": time_facts}}

    def _gather_hardware(
        self, task_vars: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Gather hardware information from dmidecode.

        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns dict[str, Any]: Hardware facts
        """
        cmd_result = self._command(
            ["dmidecode"], task_vars=task_vars, check_mode=False
        )

        if cmd_result.get("rc") != 0:
            raise AnsibleActionFail(
                "dmidecode command failed: " f"{cmd_result.get('stderr', '')}"
            )

        hardware = dmidecode(cmd_result.get("stdout", ""))

        hw_facts = {}
        for key in (
            "baseboard",
            "processors",
            "memory",
            "chassis",
            "power",
        ):
            if key in hardware:
                hw_facts[key] = hardware[key]

        return {"o0_hardware": hw_facts}

    def _gather_compliance(
        self, task_vars: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Gather POSIX/SUS compliance information.

        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns dict[str, Any]: Compliance facts
        """
        compliance_result = self._execute_module(
            module_name="o0_o.posix.compliance",
            module_args={},
            task_vars=task_vars,
        )

        if compliance_result.get("failed"):
            return {}

        compliance_data = compliance_result.get("compliance", {})
        if not compliance_data:
            return {}

        return {"o0_os": {"compliance": compliance_data}}

    def _gather_mounts(
        self, task_vars: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Gather current mount points.

        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns dict[str, Any]: Mount facts
        """
        cmd_result = self._command(["mount"], task_vars=task_vars)
        mount_output = cmd_result.get("stdout", "")
        mount_facts = mount(mount_output)

        return {"o0_storage": {"mounts": mount_facts}}

    def _gather_fstab(
        self, task_vars: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Gather /etc/fstab configuration.

        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns dict[str, Any]: Fstab facts
        """
        slurp_result = self._execute_module(
            module_name="ansible.builtin.slurp",
            module_args={"src": "/etc/fstab"},
            task_vars=task_vars,
        )

        if slurp_result.get("failed"):
            return {}

        fstab_facts = fstab(slurp_result)

        return {"o0_storage": {"config": {"/etc/fstab": fstab_facts}}}

    def _gather_users(
        self, task_vars: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Gather user and group information.

        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns dict[str, Any]: User/group facts
        """
        passwd_slurp = self._execute_module(
            module_name="ansible.builtin.slurp",
            module_args={"src": "/etc/passwd"},
            task_vars=task_vars,
        )

        group_slurp = self._execute_module(
            module_name="ansible.builtin.slurp",
            module_args={"src": "/etc/group"},
            task_vars=task_vars,
        )

        shells_slurp = self._execute_module(
            module_name="ansible.builtin.slurp",
            module_args={"src": "/etc/shells"},
            task_vars=task_vars,
        )

        facts = {"o0_os": {}}

        if not passwd_slurp.get("failed"):
            facts["o0_os"]["users"] = passwd_info(passwd_slurp)

        if not group_slurp.get("failed"):
            facts["o0_os"]["groups"] = group_info(group_slurp)

        if not shells_slurp.get("failed"):
            facts["o0_os"]["shells"] = parse_shells(shells_slurp)

        return facts

    def _resolve_subsets(self, gather_subset: list[str]) -> set[str]:
        """Resolve gather_subset into individual subsets.

        :param list[str] gather_subset: List of subset specs
        :returns set[str]: Set of individual subsets to gather
        """
        if all(s.startswith("!") for s in gather_subset):
            selected = set(self.SUBSET_METHODS.keys())
        else:
            selected = set()

        for subset in gather_subset:
            if subset == "all":
                selected.update(self.SUBSET_GROUPS["all"])
            elif subset == "min":
                selected.update(self.SUBSET_GROUPS["min"])
            elif subset == "storage":
                selected.update(self.SUBSET_GROUPS["storage"])
            elif subset == "!all":
                selected.clear()
            elif subset.startswith("!"):
                selected.discard(subset[1:])
            elif subset in self.SUBSET_METHODS:
                selected.add(subset)
            else:
                raise AnsibleActionFail(f"Invalid gather_subset: {subset}")

        return selected

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute fact gathering for selected subsets.

        :param Optional[str] tmp: Unused temporary directory path
        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns dict[str, Any]: Result dictionary with ansible_facts
        """
        task_vars = task_vars or {}
        self._def_inventory_hostname(task_vars)

        result = super().run(tmp, task_vars=task_vars)
        del tmp  # unused

        # Validate arguments
        argument_spec = {
            "gather_subset": {
                "type": "list",
                "elements": "str",
                "default": ["all"],
            }
        }
        validation_result, new_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )
        result["invocation"] = self._task.args.copy()

        # Resolve subsets
        selected_subsets = self._resolve_subsets(new_args["gather_subset"])

        self._display.vvv(
            f"Gathering fact subsets: {', '.join(sorted(selected_subsets))}"
        )

        # Gather facts for each selected subset
        all_facts = {}

        for subset in selected_subsets:
            if subset not in self.SUBSET_METHODS:
                continue

            method_name = self.SUBSET_METHODS[subset]
            gather_method = getattr(self, method_name)

            try:
                subset_facts = gather_method(task_vars=task_vars)

                # Deep merge subset_facts into all_facts
                for ns, ns_facts in subset_facts.items():
                    if ns not in all_facts:
                        all_facts[ns] = {}
                    for key, value in ns_facts.items():
                        if (
                            key in all_facts[ns]
                            and isinstance(all_facts[ns][key], dict)
                            and isinstance(value, dict)
                        ):
                            all_facts[ns][key].update(value)
                        else:
                            all_facts[ns][key] = value

            except AnsibleConnectionFailure:
                raise
            except Exception as e:
                self._display.warning(
                    f"[{self.inventory_hostname}] "
                    f"Failed to gather {subset} facts: {e}"
                )

        result["ansible_facts"] = all_facts
        result["changed"] = False

        return result
