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
    ReadPosixActionBase,
    compose_homes,
    compose_shell_files,
    compose_users_groups,
    fstab,
    get_compliance_command_requests,
    get_dmidecode_command_requests,
    get_effective_uid_command_requests,
    get_env_command_requests,
    get_mount_command_requests,
    get_timezone_command_requests,
    parse_shells,
    process_all_compliance_command_results,
    process_dmidecode_command_results,
    process_effective_uid_results,
    process_env_command_results,
    process_mount_command_results,
    process_timezone_command_results,
)
from ansible_collections.o0_o.posix.plugins.module_utils.uname_utils import (
    get_uname_command_requests,
    process_uname_command_results,
)

# All environment variables named in IEEE Std 1003.1 (POSIX)
POSIX_ENV_VARS = [
    # Mandatory (shall be set)
    "HOME",
    "LOGNAME",
    "PATH",
    # Shell-maintained
    "PWD",
    "OLDPWD",
    "IFS",
    "PPID",
    "OPTARG",
    "OPTIND",
    # Shell prompts
    "PS1",
    "PS2",
    "PS4",
    # Locale
    "LANG",
    "LC_ALL",
    "LC_COLLATE",
    "LC_CTYPE",
    "LC_MESSAGES",
    "LC_MONETARY",
    "LC_NUMERIC",
    "LC_TIME",
    # User environment
    "SHELL",
    "USER",
    "TERM",
    "TZ",
    "TMPDIR",
    "MAIL",
    "MAILCHECK",
    "MAILPATH",
    # Editors and pagers
    "EDITOR",
    "VISUAL",
    "PAGER",
    "FCEDIT",
    # Shell configuration
    "CDPATH",
    "ENV",
    "HISTFILE",
    "HISTSIZE",
    # Terminal
    "COLUMNS",
    "LINES",
    # Internationalization
    "NLSPATH",
    # Compilation and build
    "CC",
    "CFLAGS",
    "LDFLAGS",
    "ARFLAGS",
    "YACC",
    "YFLAGS",
    "LEX",
    "LFLAGS",
    "MAKEFLAGS",
    "GET",
    "GFLAGS",
    # Printing
    "LPDEST",
    # Editor init
    "EXINIT",
]


def _get_environment_requests() -> list[dict[str, Any]]:
    """Build command requests for POSIX environment collection.

    The effective UID travels with the environment because it is the
    key the results nest under.

    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    return (
        get_env_command_requests(POSIX_ENV_VARS)
        + get_effective_uid_command_requests()
    )


def _process_environment_results(
    cmds_completed: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[Exception]]:
    """Process environment results into o0_users namespace.

    Returns raw env data — the caller is responsible for keying
    it under the effective UID.

    :param list[dict[str, Any]] cmds_completed: Command results
    :returns tuple[dict[str, Any], list[Exception]]: Tuple of
        (env_dict, errors) where env_dict maps var names to values
    """
    env_data = process_env_command_results(
        cmds_completed, POSIX_ENV_VARS, False
    )
    return env_data, []


class ActionModule(ReadPosixActionBase, ActionBase):
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
        "min": {
            "uname",
            "environment",
            "timezone",
            "compliance",
        },
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

    # Subsets whose results go under o0_users[effective_uid]
    USER_SCOPED_SUBSETS = {"environment"}

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

        A namespace is not required to hold a mapping.  o0_shells is
        the list of paths named in /etc/shells, so a namespace whose
        value is anything but a dict is published whole and the last
        producer to answer wins.

        :param dict[str, Any] all_facts: Accumulator to merge into
        :param dict[str, Any] subset_facts: Facts to merge
        """
        for ns, ns_facts in subset_facts.items():
            if not isinstance(ns_facts, dict):
                all_facts[ns] = ns_facts
                continue
            if not isinstance(all_facts.get(ns), dict):
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

    def _read_files(
        self,
        paths: list[str],
        task_vars: Optional[dict[str, Any]] = None,
    ) -> dict[str, Optional[str]]:
        """Read the named files in a single round trip.

        The module gathers facts from hosts that have no Python, so a
        file a fact is read from is read the way every other fact is
        gathered: a batched command with the raw fallback under it,
        never slurp.  A file that did not answer reads None, leaving
        the facts it feeds unpublished rather than guessed at.

        :param list[str] paths: Paths to read
        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns dict[str, Optional[str]]: Content per path, None
            where the read failed
        """
        results = self._run(
            {path: ["cat", path] for path in paths},
            parallel=True,
            fail_fast=False,
            task_vars=task_vars,
            check_mode=False,
        )

        contents: dict[str, Optional[str]] = {}
        for path in paths:
            result = results.get(path) or {}
            if result.get("rc") == 0:
                contents[path] = result.get("stdout") or ""
            else:
                contents[path] = None

        return contents

    def _gather_fstab(
        self, task_vars: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Gather /etc/fstab configuration.

        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns dict[str, Any]: Fstab facts
        """
        content = self._read_files(["/etc/fstab"], task_vars)["/etc/fstab"]

        if content is None:
            return {}

        return {"o0_storage": {"config": {"/etc/fstab": fstab(content)}}}

    def _gather_users(
        self, task_vars: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Gather user, group, home and shell information.

        Every fact here comes from the same composition the users
        module publishes, so both producers emit one shape under one
        set of names.  The module additionally reads each user's SSH
        keys into their o0_users entry; a gather does not, because the
        cost is per user and the answer is not what a gather is for.

        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns dict[str, Any]: User, group, shell and home facts
        """
        contents = self._read_files(
            ["/etc/passwd", "/etc/group", "/etc/shells"], task_vars
        )
        passwd = contents["/etc/passwd"]
        group = contents["/etc/group"]
        shells = contents["/etc/shells"]

        facts = {}

        # The canonical shape cross-references both files, so it needs
        # both reads to have landed.
        if passwd is not None and group is not None:
            users, groups = compose_users_groups(passwd, group)

            def read(paths: list[str]) -> dict[str, Any]:
                return self._read(paths=paths, task_vars=task_vars)

            facts["o0_users"] = users
            facts["o0_groups"] = groups
            facts["o0_homes"] = compose_homes(users, read)
            facts["o0_shell_files"] = compose_shell_files(
                users, read, (task_vars or {}).get("o0_shell_files")
            )

        if shells is not None:
            facts["o0_shells"] = parse_shells(shells)

        return facts

    def _expand_group(self, group: str) -> set[str]:
        """Expand a subset group into the subsets it names.

        A group may name another group — ``all`` names ``storage`` —
        so expansion repeats until only subsets are left.  A group
        that names itself, directly or through another group, is
        expanded once.

        :param str group: Group name to expand
        :returns set[str]: The subsets the group resolves to
        :raises AnsibleActionFail: If a group names something that is
            neither a group nor a subset
        """
        subsets: set[str] = set()
        expanded: set[str] = set()
        pending = [group]

        while pending:
            name = pending.pop()
            if name in expanded:
                continue
            expanded.add(name)

            for member in self.SUBSET_GROUPS[name]:
                if member in self.SUBSET_GROUPS:
                    pending.append(member)
                elif member in self.SUBSET_METHODS:
                    subsets.add(member)
                else:
                    raise AnsibleActionFail(
                        f"Subset group {name} names {member}, which is"
                        f" neither a subset nor a group"
                    )

        return subsets

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
            if subset == "!all":
                selected.clear()
            elif subset.startswith("!") and subset[1:] in self.SUBSET_GROUPS:
                selected.difference_update(self._expand_group(subset[1:]))
            elif subset.startswith("!"):
                selected.discard(subset[1:])
            elif subset in self.SUBSET_GROUPS:
                selected.update(self._expand_group(subset))
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
        places them under ``o0_users[<effective uid>]['environment']``.

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

                    # User-scoped subsets nest under o0_users, which
                    # keys on the UID
                    if subset in self.USER_SCOPED_SUBSETS:
                        uid = process_effective_uid_results(run_results)
                        if uid is None:
                            self._display.warning(
                                f"[{self.inventory_hostname}] Could"
                                f" not determine the effective uid;"
                                f" dropping {subset} facts"
                            )
                            continue

                        entry = {"uid": uid, subset: facts}

                        # Validate LOGNAME/USER
                        if subset == "environment":
                            user = self.effective_user
                            for var in ("LOGNAME", "USER"):
                                val = facts.get(var)
                                if val is not None and val != user:
                                    self._display.warning(
                                        f"[{self.inventory_hostname}]"
                                        f" {var}={val} does"
                                        f" not match effective"
                                        f" user {user}"
                                    )

                            # Derive locale: LC_ALL > LANG > ASCII
                            lc_all = facts.get("LC_ALL")
                            lang = facts.get("LANG")
                            locale = lc_all or lang or "ASCII"
                            if locale in ("C", "POSIX"):
                                locale = "ASCII"
                            entry["locale"] = locale

                        self._merge_facts(
                            all_facts, {"o0_users": {str(uid): entry}}
                        )
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
