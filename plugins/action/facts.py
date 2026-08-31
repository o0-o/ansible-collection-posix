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
    EVIDENCE,
    POSIX_ENV_VARS,
    SHELL_DEFAULT,
    SHELL_SYSTEM_HOME,
    ReadPosixActionBase,
    batch_read,
    commands_run,
    compose_evidence,
    compose_homes,
    compose_mount_config,
    compose_paths,
    compose_shell_paths,
    compose_shells,
    compose_users_groups,
    fstab,
    get_compliance_command_requests,
    get_dmidecode_command_requests,
    get_effective_uid_command_requests,
    get_env_command_requests,
    get_file_command_requests,
    get_getconf_command_requests,
    get_getent_command_requests,
    get_limits_command_requests,
    get_mount_command_requests,
    get_pathconf_command_requests,
    get_shell_command_requests,
    get_timezone_command_requests,
    merge_entry,
    merge_evidence,
    parse_shells,
    process_all_compliance_command_results,
    process_dmidecode_command_results,
    process_effective_uid_results,
    process_env_command_results,
    process_file_command_results,
    process_getconf_command_results,
    process_getent_command_results,
    process_limits_command_results,
    process_mount_command_results,
    process_pathconf_command_results,
    process_shell_command_results,
    process_timezone_command_results,
)
from ansible_collections.o0_o.posix.plugins.module_utils.uname_utils import (
    get_uname_command_requests,
    process_uname_command_results,
)

# The files a gather reads.  A gather reads the canonical paths; the
# modules that take a path option are where another one is named.
FSTAB_PATH = "/etc/fstab"
GROUP_PATH = "/etc/group"
PASSWD_PATH = "/etc/passwd"
SHELLS_PATH = "/etc/shells"


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


# What the user-scoped probes are run with.  Each variable is asked
# for by a command written as a shell snippet rather than as argv, so
# it names no command of its own and the subset that ran it names what
# ran it: a shell, plus the id(1) that says whose answers these are.
USER_SCOPED_COMMANDS = ("id", "sh")


def _get_limits_requests() -> list[dict[str, Any]]:
    """Build command requests for the user-scoped shell facts.

    The effective UID travels with them because it is the key the
    results nest under, the same way it travels with the environment.

    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    return (
        get_limits_command_requests() + get_effective_uid_command_requests()
    )


def _process_limits_results(
    cmds_completed: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[Exception]]:
    """Process the shell probes into the fields they file.

    Answers with the fields themselves rather than one field named
    for the subset, because a user's limits and a user's umask are
    two facts about that user.  The caller is responsible for keying
    them under the effective UID.

    :param list[dict[str, Any]] cmds_completed: Command results
    :returns tuple[dict[str, Any], list[Exception]]: Tuple of
        (fields, errors) to file on the user's entry
    """
    return process_limits_command_results(cmds_completed)


def _get_fstab_requests() -> list[dict[str, Any]]:
    """Build command requests for the filesystem table.

    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    return get_file_command_requests([FSTAB_PATH])


def _process_fstab_results(
    cmds_completed: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[Exception]]:
    """Process the fstab read into the path store.

    What a file configures is a fact about that file, so it lands at
    the file's own path in the one flat store - the bytes under
    ``content``, the filesystems they name under ``config`` - the way
    /etc/shells lands the login shells it names.  Live state is a
    different fact and keeps its own namespace: what is mounted now
    is ``o0_storage.mounts``, and what the host is configured to
    mount is this.

    A host with no /etc/fstab leaves the path out of the store
    rather than filing a null there, because a ``cat`` that failed
    does not tell a file that is not there from one that could not
    be read, and a null is the store's word for confirmed absent.

    :param list[dict[str, Any]] cmds_completed: Command results
    :returns tuple[dict[str, Any], list[Exception]]: Tuple of
        (facts_dict, errors) where facts_dict has the o0_paths
        namespace key
    """
    content = (
        process_file_command_results(cmds_completed).get(FSTAB_PATH) or {}
    ).get("parsed")

    if content is None:
        return {}, []

    return {
        "o0_paths": {
            FSTAB_PATH: {"content": content, "config": fstab(content)}
        }
    }, []


def _get_users_requests() -> list[dict[str, Any]]:
    """Build command requests for the files users are named in.

    The host's own resolved view of those users travels in the same
    batch: getent is a command like any other, and asking for it costs
    a gather nothing it was not already spending.

    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    return (
        get_file_command_requests([PASSWD_PATH, GROUP_PATH, SHELLS_PATH])
        + get_getent_command_requests()
    )


def _process_users_results(
    cmds_completed: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[Exception]]:
    """Process the user files into the facts they compose.

    Every fact here comes from the same composition the users module
    publishes, so both producers emit one shape under one set of
    names.  The module additionally reads each user's SSH keys into
    their o0_users entry; a gather does not, because the cost is per
    user and the answer is not what a gather is for.

    /etc/shells is a single file parsed on its own, so it lands at
    its own path in the store: the bytes under ``content``, the login
    shells they name under ``config``.  The homes and shell files the
    passwd entries name are read after this batch, because a path is
    only known to be there once it has been read.

    :param list[dict[str, Any]] cmds_completed: Command results
    :returns tuple[dict[str, Any], list[Exception]]: Tuple of
        (facts_dict, errors) where facts_dict has the o0_users,
        o0_groups and o0_paths namespace keys
    """
    files = process_file_command_results(cmds_completed)
    passwd = (files.get(PASSWD_PATH) or {}).get("parsed")
    group = (files.get(GROUP_PATH) or {}).get("parsed")
    shells = (files.get(SHELLS_PATH) or {}).get("parsed")
    resolved = process_getent_command_results(cmds_completed)

    facts: dict[str, Any] = {}

    # The canonical shape cross-references both files, so it needs
    # both reads to have landed.  The resolved view is what the host
    # says about itself over that base, and a host with no getent
    # answers None for it, which composes the files-only facts.
    if passwd is not None and group is not None:
        users, groups = compose_users_groups(
            passwd,
            group,
            resolved.get("passwd"),
            resolved.get("group"),
            passwd_path=PASSWD_PATH,
            group_path=GROUP_PATH,
        )
        facts["o0_users"] = users
        facts["o0_groups"] = groups

    if shells is not None:
        named = parse_shells(shells)
        facts["o0_paths"] = {
            SHELLS_PATH: {
                "content": shells,
                "config": named,
            }
        }
        facts["o0_shells"] = compose_shells(named)

    return facts, []


class ActionModule(ReadPosixActionBase, ActionBase):
    """Gather comprehensive POSIX facts from the managed host.

    Collects system information using shell commands and file reads,
    organized into logical namespaces: o0_os, o0_hardware,
    o0_storage, o0_network, and o0_users.

    Every subset is a set of command requests and a processor that
    reads their results, so a gather of any size is one parallel
    ``_run()`` call.  The files a subset reads travel in that batch
    beside the probes, which is why reading four of them costs
    nothing over reading none.
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
            "limits",
            "timezone",
            "dmidecode",
            "compliance",
            "config",
            "storage",
            "users",
        },
        "storage": {"mounts", "fstab"},
    }

    # Every subset, each naming the requests it puts in the batch and
    # the processor that reads their results back out
    SUBSETS = {
        "uname": {
            "requests": get_uname_command_requests,
            "processor": process_uname_command_results,
        },
        "compliance": {
            "requests": get_compliance_command_requests,
            "processor": process_all_compliance_command_results,
        },
        "config": {
            "requests": get_getconf_command_requests,
            "processor": process_getconf_command_results,
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
        "limits": {
            "requests": _get_limits_requests,
            "processor": _process_limits_results,
        },
        "fstab": {
            "requests": _get_fstab_requests,
            "processor": _process_fstab_results,
        },
        "users": {
            "requests": _get_users_requests,
            "processor": _process_users_results,
        },
    }

    # Subsets whose results go under o0_users[effective_uid].  Every
    # one of them describes the user the play connects as and no
    # other: another user's environment, limits and umask are what a
    # run delegated to that user answers, and reading this user's is
    # not an answer about theirs.
    USER_SCOPED_SUBSETS = {"environment", "limits"}

    # Of those, the ones whose processor answers with the fields to
    # file on the entry rather than with one field named for the
    # subset.  A user's limits and a user's umask are two facts about
    # that user, not two parts of a thing called limits.
    USER_SCOPED_FIELDS = {"limits"}

    # The namespace that has a composer of its own
    PATHS_NAMESPACE = "o0_paths"

    # What this module is called, which is what a path entry names as
    # having contributed it
    FQCN = "o0_o.posix.facts"

    def _merge_facts(
        self,
        all_facts: dict[str, Any],
        subset_facts: dict[str, Any],
    ) -> None:
        """Deep merge subset facts into the accumulator.

        o0_paths merges through ``compose_paths``, the one composer
        that owns it: the store is flat absolute-path keys, and an
        entry is one observation of one path, so a later observation
        replaces an earlier one whole rather than blending its fields
        into it.  Blending is what this merge does everywhere else,
        and a path entry blended across two observations would
        describe a file that never existed.

        A namespace is not required to hold a mapping.  A namespace
        whose value is anything but a dict is published whole and the
        last producer to answer wins.

        Evidence is the one thing a later producer adds to rather than
        replaces.  Several subsets answer for one namespace - uname,
        the clock and the configuration sweep all publish under
        ``o0_os`` - and each names what it consulted, so a merge that
        let the last of them win would publish a namespace claiming a
        fraction of what was gathered for it.  The same holds one
        level down, where a user's entry is composed from the files
        and then added to by the subsets that describe the user the
        play is running as.

        :param dict[str, Any] all_facts: Accumulator to merge into
        :param dict[str, Any] subset_facts: Facts to merge
        """
        for ns, ns_facts in subset_facts.items():
            if ns == self.PATHS_NAMESPACE:
                all_facts[ns] = compose_paths(
                    all_facts.get(ns), ns_facts, origin=self.FQCN
                )
                continue
            if not isinstance(ns_facts, dict):
                all_facts[ns] = ns_facts
                continue
            if not isinstance(all_facts.get(ns), dict):
                all_facts[ns] = {}
            for key, value in ns_facts.items():
                known = all_facts[ns].get(key)
                if not (isinstance(known, dict) and isinstance(value, dict)):
                    all_facts[ns][key] = value
                elif key == EVIDENCE:
                    merge_evidence(known, value)
                else:
                    merge_entry(known, value)

    def _second_batch(
        self,
        mounts: dict[str, Any],
        pairs: list[tuple[str, str]],
        task_vars: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Ask everything that had to wait for the first batch.

        Two questions are asked at paths the first batch answered
        with, so neither could have ridden it: what each mounted
        filesystem says about itself, asked at its mountpoint, and
        what each login shell produces, asked by running it out of a
        home.  They are asked together because they are asked at the
        same moment for the same reason, and one round trip answers
        both.

        Each is composed where both producers of its fact compose it,
        so the mounts module and the users module attach the same
        answers to the same entries.

        :param dict[str, Any] mounts: The composed mounts fact, or an
            empty mapping where the mounts subset did not run
        :param list[tuple[str, str]] pairs: The (shell, home)
            combinations to observe
        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns dict[str, Any]: The namespaces the answers compose
        """
        requests = []
        if mounts:
            requests.extend(get_pathconf_command_requests(sorted(mounts)))
        if pairs:
            requests.extend(get_shell_command_requests(pairs))

        if not requests:
            return {}

        self._display.vvv(
            f"Asking {len(requests)} command(s) of"
            f" {len(mounts)} mountpoint(s) and"
            f" {len(pairs)} shell context(s)"
        )

        run_results = self._run(
            requests,
            parallel=True,
            fail_fast=False,
            task_vars=task_vars,
            check_mode=False,
        )

        facts: dict[str, Any] = {}

        if mounts:
            facts["o0_storage"] = {
                "mounts": compose_mount_config(
                    mounts, process_pathconf_command_results(run_results)
                ),
                # What each filesystem answers is asked of it the same
                # way the host's own configuration is asked, and the
                # answers are the fact rather than evidence for one
                "evidence": compose_evidence(
                    commands=commands_run(run_results, "getconf_pathconf")
                ),
            }

        if pairs:
            shells = compose_shells(
                None,
                process_shell_command_results(run_results),
                compose_evidence(
                    commands=commands_run(run_results, "shell_config")
                ),
            )
            if shells:
                facts["o0_shells"] = shells

        return facts

    def _shell_pairs(
        self,
        shell: str,
        all_facts: dict[str, Any],
        uid: Optional[int],
    ) -> list[tuple[str, str]]:
        """Name the combinations this gather has reason to observe.

        Two of them at most.  The system layer is the shell the task
        named, run out of the canonical home no host has: what a login
        shell does before any user's dot files enter into it.  The
        user layer is the connecting user's own login shell run out of
        their own home, which is what they actually get.

        A shell the path store has confirmed absent is not probed.
        The store is consulted rather than trusted for a positive: a
        path it has never been asked about is not a path known to be
        missing, and the probe answers that question itself.

        :param str shell: The shell the task named for the system
            layer
        :param dict[str, Any] all_facts: What the gather has composed
            so far
        :param Optional[int] uid: The effective uid, where one was
            determined
        :returns list[tuple[str, str]]: The (shell, home) pairs to
            observe
        """
        paths = all_facts.get(self.PATHS_NAMESPACE) or {}

        def absent(path: str) -> bool:
            return path in paths and paths[path] is None

        pairs = []
        if shell and not absent(shell):
            pairs.append((shell, SHELL_SYSTEM_HOME))

        entry = (all_facts.get("o0_users") or {}).get(str(uid)) or {}
        user_shell = entry.get("shell")
        user_home = entry.get("home")
        if user_shell and user_home and not absent(user_shell):
            pair = (user_shell, user_home)
            if pair not in pairs:
                pairs.append(pair)

        return pairs

    def _read_user_paths(
        self,
        users: dict[str, Any],
        task_vars: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Read the paths the passwd entries named.

        Homes and shell files are both metadata reads over paths a
        passwd line already named, so they are read together, in one
        batch.  That batch cannot join the batch that read
        /etc/passwd: the paths are not known until that read has been
        parsed, and a path is only known to be there once it has been
        read.

        A home is a path and so is a shell, so both are entries of
        ``o0_paths`` rather than namespaces of their own, and a shell
        that resolves through links puts every step of the chain in
        the store beside it.

        :param dict[str, Any] users: The o0_users mapping the batch
            composed
        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns dict[str, Any]: The home and shell entries of the
            path store
        """

        def read_paths(paths: list[str]) -> dict[str, Any]:
            # Every read resolves, because the question a consumer has
            # about a shell is what it really is, and a home reached
            # through a link is the same question
            return self._read(
                paths=paths, task_vars=task_vars, resolve=True
            )

        known_paths = (task_vars or {}).get("o0_paths")
        read = batch_read(users, read_paths, known_paths)

        paths = compose_paths(None, compose_homes(users, read))
        paths = compose_paths(
            paths, compose_shell_paths(users, read, known_paths)
        )

        return {"o0_paths": paths} if paths else {}

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
                elif member in self.SUBSETS:
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
            selected = set(self.SUBSETS.keys())
        else:
            selected = set()

        for subset in gather_subset:
            if subset == "!all":
                selected.clear()
            elif subset.startswith("!") and subset[1:] in self.SUBSET_GROUPS:
                selected.difference_update(self._expand_group(subset[1:]))
            elif subset.startswith("!"):
                # A typo'd exclusion silently gathering what it meant
                # to exclude is worse than a typo'd selection: unknown
                # names fail in both polarities
                if subset[1:] not in self.SUBSETS:
                    raise AnsibleActionFail(f"Invalid gather_subset: {subset}")
                selected.discard(subset[1:])
            elif subset in self.SUBSET_GROUPS:
                selected.update(self._expand_group(subset))
            elif subset in self.SUBSETS:
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

        Every selected subset's requests are aggregated and executed
        in a single parallel ``_run()`` call, the files they read
        included.  What is asked at a path the batch itself answered
        with comes after it: the configuration of each mounted
        filesystem, and the homes and shell files the users subset
        publishes.

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
            },
            "shell": {
                "type": "str",
                "default": SHELL_DEFAULT,
            },
        }
        validation_result, new_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )
        result["invocation"] = self._task.args.copy()

        selected_subsets = self._resolve_subsets(new_args["gather_subset"])

        self._display.vvv(
            f"Gathering fact subsets: {', '.join(sorted(selected_subsets))}"
        )

        all_facts = {}
        user_facts: dict[str, Any] = {}
        effective_uid: Optional[int] = None

        # Phase 1: Aggregate and execute every selected subset
        if selected_subsets:
            all_requests = []
            for subset in selected_subsets:
                spec = self.SUBSETS[subset]
                requests = spec["requests"]()
                self._display.vvv(
                    f"Batched {subset}: {len(requests)} command(s)"
                )
                all_requests.extend(requests)

            self._display.vvv(
                f"Executing {len(all_requests)} batched "
                f"command(s) for "
                f"{', '.join(sorted(selected_subsets))}"
            )

            run_results = self._run(
                all_requests,
                parallel=True,
                fail_fast=False,
                task_vars=task_vars,
                check_mode=False,
            )

            for subset in selected_subsets:
                spec = self.SUBSETS[subset]
                try:
                    facts, errors = spec["processor"](run_results)
                    for err in errors:
                        self._display.warning(
                            f"[{self.inventory_hostname}] {err}"
                        )

                    # Kept for the read that follows the batch
                    if subset == "users":
                        user_facts = facts

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

                        effective_uid = uid
                        entry: dict[str, Any] = {
                            "uid": uid,
                            EVIDENCE: compose_evidence(
                                commands=USER_SCOPED_COMMANDS
                            ),
                        }
                        if subset in self.USER_SCOPED_FIELDS:
                            entry.update(facts)
                        else:
                            entry[subset] = facts

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

        # Phase 2: Ask about the paths the batch had to answer with
        # before they could be asked about - the mountpoints df named,
        # and the shells the task and the passwd entries named. The
        # shells belong to the users subset, which is where /etc/shells
        # is read, so that min stays the one round trip it promises.
        self._merge_facts(
            all_facts,
            self._second_batch(
                (all_facts.get("o0_storage") or {}).get("mounts") or {},
                (
                    self._shell_pairs(
                        new_args["shell"], all_facts, effective_uid
                    )
                    if "users" in selected_subsets
                    else []
                ),
                task_vars,
            ),
        )

        # Phase 3: Read the paths the passwd entries named, which is a
        # metadata read rather than a command and cannot join a batch
        if user_facts.get("o0_users"):
            self._merge_facts(
                all_facts,
                self._read_user_paths(user_facts["o0_users"], task_vars),
            )

        result["ansible_facts"] = all_facts
        result["changed"] = False

        return result
