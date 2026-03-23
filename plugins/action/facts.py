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

from ansible.errors import AnsibleActionFail, AnsibleConnectionFailure
from ansible.plugins.action import ActionBase

from ansible_collections.o0_o.posix.plugins.module_utils import (
    PosixActionBase,
    fstab,
    get_compliance_command_requests,
    get_dmidecode_command_requests,
    get_env_command_requests,
    get_mount_command_requests,
    get_timezone_command_requests,
    group_info,
    parse_shells,
    passwd_info,
    process_all_compliance_command_results,
    process_dmidecode_command_results,
    process_env_command_results,
    process_mount_command_results,
    process_timezone_command_results,
)
from ansible_collections.o0_o.posix.plugins.module_utils.uname_utils import (
    get_uname_command_requests,
    process_uname_command_results,
)

# POSIX-defined environment variables to collect
POSIX_ENV_VARS = [
    # Mandatory (shall be set)
    "HOME",
    "LOGNAME",
    "PATH",
    # Shell-maintained
    "PWD",
    "OLDPWD",
    # Commonly defined by POSIX
    "SHELL",
    "USER",
    "TERM",
    "LANG",
    "LC_ALL",
    "LC_COLLATE",
    "LC_CTYPE",
    "LC_MESSAGES",
    "LC_MONETARY",
    "LC_NUMERIC",
    "LC_TIME",
    "TZ",
    "TMPDIR",
    "EDITOR",
    "VISUAL",
    "PAGER",
    "MAIL",
    "CDPATH",
    "ENV",
    "COLUMNS",
    "LINES",
    "IFS",
]


def _get_environment_requests() -> list[dict[str, Any]]:
    """Build command requests for POSIX environment collection.

    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    return get_env_command_requests(POSIX_ENV_VARS)


def _process_environment_results(
    cmds_completed: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[Exception]]:
    """Process environment results into o0_users namespace.

    Returns raw env data — the caller is responsible for keying
    it under the effective username.

    :param list[dict[str, Any]] cmds_completed: Command results
    :returns tuple[dict[str, Any], list[Exception]]: Tuple of
        (env_dict, errors) where env_dict maps var names to values
    """
    env_data = process_env_command_results(
        cmds_completed, POSIX_ENV_VARS, False
    )
    return env_data, []


class ActionModule(PosixActionBase, ActionBase):
    """Gather comprehensive POSIX facts from the managed host.

    Collects system information using shell commands and file reads,
    organized into logical namespaces: o0_os, o0_hardware,
    o0_storage, o0_network, and o0_users.

    Subsets with COMMAND_SPEC support are batched into a single
    parallel ``_run()`` call.  Remaining subsets use individual
    gather methods.
    """

    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False
    _supports_diff = False

    # Subset groups
    SUBSET_GROUPS = {
        "min": {"uname", "environment", "timezone", "compliance"},
        "all": {
            "uname",
            "environment",
            "timezone",
            "dmidecode",
            "compliance",
            "storage",
            "users",
        },
        "storage": {"mounts", "fstab"},
    }

    # Subsets that use the COMMAND_SPEC batched path
    BATCHED_SUBSETS = {
        "uname": {
            "requests": get_uname_command_requests,
            "processor": process_uname_command_results,
        },
        "compliance": {
            "requests": get_compliance_command_requests,
            "processor": process_all_compliance_command_results,
        },
        "dmidecode": {
            "requests": get_dmidecode_command_requests,
            "processor": process_dmidecode_command_results,
        },
        "mounts": {
            "requests": get_mount_command_requests,
            "processor": process_mount_command_results,
        },
        "timezone": {
            "requests": get_timezone_command_requests,
            "processor": process_timezone_command_results,
        },
        "environment": {
            "requests": _get_environment_requests,
            "processor": _process_environment_results,
        },
    }

    # Subsets that use individual gather methods (legacy path)
    LEGACY_METHODS = {
        "fstab": "_gather_fstab",
        "users": "_gather_users",
    }

    # All valid subsets (union of both)
    SUBSET_METHODS = {
        **{k: None for k in BATCHED_SUBSETS},
        **LEGACY_METHODS,
    }

    def _merge_facts(
        self,
        all_facts: dict[str, Any],
        subset_facts: dict[str, Any],
    ) -> None:
        """Deep merge subset facts into the accumulator.

        :param dict[str, Any] all_facts: Accumulator to merge into
        :param dict[str, Any] subset_facts: Facts to merge
        """
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

        facts = {}

        if not passwd_slurp.get("failed"):
            facts["o0_users"] = passwd_info(passwd_slurp, key="name")

        if not group_slurp.get("failed"):
            facts["o0_groups"] = group_info(group_slurp)

        if not shells_slurp.get("failed"):
            facts["o0_shells"] = parse_shells(shells_slurp)

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

        Batched subsets are aggregated and executed in a single
        parallel ``_run()`` call.  Legacy subsets run individually.

        The ``environment`` subset collects POSIX env vars and
        places them under ``o0_users[effective_user]['environment']``.

        :param Optional[str] tmp: Unused temporary directory path
        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns dict[str, Any]: Result dictionary with ansible_facts
        """
        task_vars = task_vars or {}
        self._def_inventory_hostname(task_vars)
        self._def_effective_user(task_vars)

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

        selected_subsets = self._resolve_subsets(new_args["gather_subset"])

        self._display.vvv(
            "Gathering fact subsets: " f"{', '.join(sorted(selected_subsets))}"
        )

        all_facts = {}

        # Phase 1: Aggregate and execute batched subsets
        batched_selected = selected_subsets & self.BATCHED_SUBSETS.keys()
        if batched_selected:
            all_requests = []
            for subset in batched_selected:
                spec = self.BATCHED_SUBSETS[subset]
                requests = spec["requests"]()
                self._display.vvv(
                    f"Batched {subset}: " f"{len(requests)} command(s)"
                )
                all_requests.extend(requests)

            self._display.vvv(
                f"Executing {len(all_requests)} batched "
                f"command(s) for "
                f"{', '.join(sorted(batched_selected))}"
            )

            run_results = self._run(
                all_requests,
                parallel=True,
                fail_fast=False,
                task_vars=task_vars,
                check_mode=False,
            )

            for subset in batched_selected:
                spec = self.BATCHED_SUBSETS[subset]
                try:
                    facts, errors = spec["processor"](run_results)
                    for err in errors:
                        self._display.warning(
                            f"[{self.inventory_hostname}] " f"{err}"
                        )

                    # Environment goes under o0_users
                    if subset == "environment":
                        user = self.effective_user
                        env_facts = {
                            "o0_users": {user: {"environment": facts}}
                        }

                        # Warn if LOGNAME/USER mismatch
                        logname = facts.get("LOGNAME")
                        env_user = facts.get("USER")
                        for var, val in [
                            ("LOGNAME", logname),
                            ("USER", env_user),
                        ]:
                            if val is not None and val != user:
                                self._display.warning(
                                    f"[{self.inventory_hostname}]"
                                    f" {var}={val} does not"
                                    f" match effective user"
                                    f" {user}"
                                )

                        self._merge_facts(all_facts, env_facts)
                    else:
                        self._merge_facts(all_facts, facts)

                except Exception as e:
                    self._display.warning(
                        f"[{self.inventory_hostname}] "
                        f"Failed to process {subset}: {e}"
                    )

        # Phase 2: Execute legacy subsets individually
        legacy_selected = selected_subsets & self.LEGACY_METHODS.keys()
        for subset in legacy_selected:
            method_name = self.LEGACY_METHODS[subset]
            gather_method = getattr(self, method_name)

            try:
                subset_facts = gather_method(task_vars=task_vars)
                self._merge_facts(all_facts, subset_facts)
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
