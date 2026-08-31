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

from ansible.plugins.action import ActionBase

from ansible_collections.o0_o.posix.plugins.module_utils import (
    EVIDENCE,
    SHELL_DEFAULT,
    ShellsPosixActionBase,
    compose_evidence,
    compose_paths,
    compose_shell_paths,
    compose_shells,
    get_effective_uid_command_requests,
    get_file_command_requests,
    name_origins,
    name_shell_binaries,
    parse_shells,
    process_effective_uid_results,
    process_file_command_results,
)

# The file a host names its login shells in
SHELLS_PATH = "/etc/shells"

# What that file's own entry was consulted with.  The bytes under
# ``content`` and the names under ``config`` both came out of one read
# of the file, and the file is the fact rather than evidence for
# itself, so the entry names the command that read it and no path.
FILE_READ_COMMANDS = ("cat",)

# What this module is called, which is what an entry names as having
# contributed it
FQCN = "o0_o.posix.shells"


class ActionModule(ShellsPosixActionBase, ActionBase):
    """Run a host's login shells and report what they do.

    The names come out of ``/etc/shells``, which is the host's claim
    about which shells a login may use.  What each one does is only
    knowable by running it, so this runs them: the shell the task
    named out of the canonical home no host has, and the login of each
    identity this run can reach, each out of its own home.

    Which is what separates this from M(o0_o.posix.users), which
    reads the same file and publishes the same keys with nothing under
    them.  The planning and the composition are shared with
    M(o0_o.posix.facts), so a gather and this module cannot disagree
    about what a shell turned out to do.

    What a previous gather published is consulted rather than asked
    for again: a shell the path store has confirmed absent is not run,
    and on a run that cannot drop into a login the connecting user's
    own pair is named from their passwd entry, which is a fact this
    module does not read for itself.
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
        """Name the host's login shells and run what it can of them.

        :param Optional[str] tmp: Unused temporary directory path
        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns dict[str, Any]: Result with the shells under
            'shells', the paths it described under 'o0_paths', and
            ansible_facts where gather was asked for
        """
        task_vars = task_vars or {}
        self._def_inventory_hostname(task_vars)
        self._def_effective_user(task_vars)

        result = super().run(tmp, task_vars=task_vars)
        del tmp  # unused

        argument_spec = {
            "shell": {
                "type": "str",
                "default": SHELL_DEFAULT,
            },
            "gather": {
                "type": "bool",
                "default": False,
            },
        }
        validation_result, new_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )
        result["invocation"] = self._task.args.copy()

        known = {
            self.PATHS_NAMESPACE: task_vars.get(self.PATHS_NAMESPACE),
            self.USERS_NAMESPACE: task_vars.get(self.USERS_NAMESPACE),
        }

        named, paths, uid = self._read_shells_file(task_vars)

        # A shell is run, not read, so the observations are a batch of
        # their own that could not have ridden the read: what to run is
        # decided by what the file named and by what the store already
        # knows is not there
        probes = self._shell_probes(new_args["shell"], known, uid)

        shells = compose_shells(named)
        if probes:
            run_results = self._run(
                probes,
                parallel=True,
                fail_fast=False,
                task_vars=task_vars,
                # Running a login shell to see what it configures
                # changes nothing, and a check mode run that skipped it
                # would read as a host whose shells do nothing
                check_mode=False,
            )
            shells = self._composed_shells(run_results, named)

        paths = compose_paths(
            paths,
            compose_shell_paths(
                {},
                lambda wanted: self._read(
                    paths=wanted,
                    task_vars=task_vars,
                    resolve=True,
                    follow=False,
                ),
                known.get(self.PATHS_NAMESPACE),
                sorted(shells),
            ),
            origin=FQCN,
        )

        # A shell entry points at the file its name resolves to,
        # copied from the chain the path store already walked
        name_shell_binaries(shells, paths)

        facts: dict[str, Any] = {}
        if shells:
            facts["o0_shells"] = name_origins(shells, FQCN)
        if paths:
            facts[self.PATHS_NAMESPACE] = paths

        result.update(
            {
                "changed": False,
                # A host that names no login shells and would run none
                # leaves the answer empty rather than absent: the
                # module was asked and this is what it got
                "shells": facts.get("o0_shells") or {},
                self.PATHS_NAMESPACE: paths or {},
            }
        )

        if new_args.get("gather", False) and facts:
            result["ansible_facts"] = facts

        return result

    def _read_shells_file(
        self,
        task_vars: Optional[dict[str, Any]] = None,
    ) -> tuple[
        Optional[list[str]], dict[str, Any], Optional[int]
    ]:
        """Read the file the host names its login shells in.

        The effective uid rides with the read, because whether a login
        can be dropped into and whose passwd entry names the fallback
        pair both turn on who this run is.

        The file lands at its own path in the store - the bytes under
        ``content``, the names they hold under ``config`` - because
        what a file names is a fact about that file.  A host with no
        ``/etc/shells`` leaves the path out rather than filing a null
        there: a ``cat`` that failed cannot tell a file that is not
        there from one it could not read.

        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns tuple[Optional[list[str]], dict[str, Any],
            Optional[int]]: The names the file held or None where it
            would not be read, the path entries it composed, and the
            effective uid
        """
        run_results = self._run(
            get_file_command_requests([SHELLS_PATH])
            + get_effective_uid_command_requests(),
            parallel=True,
            fail_fast=False,
            task_vars=task_vars,
            check_mode=False,
        )

        files = process_file_command_results(run_results)
        content = (files.get(SHELLS_PATH) or {}).get("parsed")
        uid = process_effective_uid_results(run_results)

        if content is None:
            return None, {}, uid

        named = parse_shells(content)
        paths = compose_paths(
            None,
            {
                SHELLS_PATH: {
                    "content": content,
                    "config": named,
                    EVIDENCE: compose_evidence(commands=FILE_READ_COMMANDS),
                }
            },
            origin=FQCN,
        )

        return named, paths, uid
