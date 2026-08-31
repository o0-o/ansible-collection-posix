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
    SYSCTL_MISSING_RCS,
    PosixActionBase,
    compose_evidence,
    get_sysctl_assignment_requests,
    get_sysctl_key_requests,
    get_sysctl_listing_requests,
    process_sysctl_command_results,
)

# What the answer consulted.  One command answers every question here,
# whether it was asked to read or to write.
SYSCTL_COMMANDS = ("sysctl",)


class ActionModule(PosixActionBase, ActionBase):
    """Read and set the kernel's own tunables.

    An inquiry, and where a value is given, a change to the running
    kernel and nothing further.  Keys and their meanings are the
    kernel's, not POSIX's, so values come back verbatim and untyped:
    what a number here signifies depends on which kernel answered.

    Persistence is deliberately out of scope. Setting a value at
    runtime is the one interface every implementation shares, so it is
    the whole of what this does; writing it somewhere a boot will read
    is per-OS business, and an OS collection's own sysctl module is
    where that option belongs, delegating the runtime set to this.
    """

    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False
    _supports_diff = True

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Read what the host says, and set what the task asked for.

        :param Optional[str] tmp: Unused temporary directory path
        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns dict[str, Any]: Result with the values under 'sysctl'
        :raises AnsibleActionFail: If the host has no sysctl, or if it
            refused a value the task asked to set
        """
        task_vars = task_vars or {}
        self._def_inventory_hostname(task_vars)

        result = super().run(tmp, task_vars=task_vars)
        del tmp  # unused

        argument_spec = {
            # The keys to report.  A list rather than one key, because
            # asking about several costs one round trip either way
            "name": {
                "type": "list",
                "elements": "str",
            },
            # The keys to set, each with the value to set it to. A
            # mapping rather than a list of assignments, so a key
            # cannot be named twice with two values in one task
            "values": {
                "type": "dict",
            },
        }
        validation_result, new_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )
        result["invocation"] = self._task.args.copy()

        named = [str(key) for key in (new_args.get("name") or [])]
        wanted = {
            str(key): "" if value is None else str(value)
            for key, value in (new_args.get("values") or {}).items()
        }

        # What the host says now, which is both the answer to a query
        # and what a set is compared against
        asked = sorted(set(named) | set(wanted))
        known = self._read(asked, task_vars)

        changing = {
            key: value
            for key, value in wanted.items()
            if known.get(key) != value
        }

        # Check mode sets nothing and claims nothing was set: what
        # comes back is what the host says now, and changed says what
        # would have happened to it
        if changing and not self._task.check_mode:
            self._assign(changing, task_vars)
            # What the kernel holds now rather than what it was asked
            # to hold: a value it normalized on the way in is its
            # answer, and the caller's string was only a request
            known.update(self._read(sorted(changing), task_vars))

        result.update(
            {
                "changed": bool(changing),
                "sysctl": known,
                EVIDENCE: compose_evidence(commands=SYSCTL_COMMANDS),
            }
        )

        if self._task.diff and changing:
            result["diff"] = [
                {
                    "before": {key: known.get(key)},
                    "after": {key: value},
                    "before_header": key,
                    "after_header": key,
                }
                for key, value in sorted(changing.items())
            ]

        return result

    def _read(
        self,
        keys: list[str],
        task_vars: Optional[dict[str, Any]] = None,
    ) -> dict[str, Optional[str]]:
        """Ask the host what it says, for these keys or for all of them.

        :param list[str] keys: The keys to ask about, or empty for
            every key the host prints
        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns dict[str, Optional[str]]: The values keyed by key
        :raises AnsibleActionFail: If the host has no sysctl
        """
        requests = (
            get_sysctl_key_requests(keys)
            if keys
            else get_sysctl_listing_requests()
        )

        run_results = self._run(
            requests,
            parallel=True,
            fail_fast=False,
            task_vars=task_vars,
            # Reading a tunable changes nothing, and a check mode run
            # that skipped it could not tell whether a set was needed
            check_mode=False,
        )

        self._refuse_a_host_without_sysctl(run_results)

        values, errors = process_sysctl_command_results(run_results, keys)

        for err in errors:
            self._display.warning(f"[{self.inventory_hostname}] {err}")

        return values

    def _assign(
        self,
        values: dict[str, str],
        task_vars: Optional[dict[str, Any]] = None,
    ) -> None:
        """Set each value, and fail naming a key the host refused.

        A read-only key and an unprivileged session both refuse, and
        either way the task asked for a change that did not happen, so
        it fails rather than reporting success over a value that never
        moved.

        :param dict[str, str] values: The value to set, keyed by key
        :param Optional[dict[str, Any]] task_vars: Task variables
        :raises AnsibleActionFail: If the host refused an assignment
        """
        run_results = self._run(
            get_sysctl_assignment_requests(values),
            parallel=True,
            fail_fast=False,
            task_vars=task_vars,
            check_mode=False,
        )

        self._refuse_a_host_without_sysctl(run_results)

        refused = sorted(
            {
                assignment.split("=", 1)[0]
                for result in run_results
                if isinstance(result, dict)
                and result.get("rc") not in (0, None)
                for assignment in [
                    (result.get("args") or {}).get("assignment") or ""
                ]
                if assignment
            }
        )

        if refused:
            raise AnsibleActionFail(
                f"The host refused to set {', '.join(refused)}. A"
                f" read-only key and an unprivileged session both"
                f" refuse, so the value asked for is not the value in"
                f" force"
            )

    def _refuse_a_host_without_sysctl(
        self, run_results: list[dict[str, Any]]
    ) -> None:
        """Fail plainly where the host has no sysctl to ask.

        A POSIX host need not have one, and an explicit inquiry may
        fail loud about it: nothing here is an overlay on a gather that
        would rather report nothing than stop.

        :param list[dict[str, Any]] run_results: The batch's results
        :raises AnsibleActionFail: If the tool is not there
        """
        statuses = {
            result.get("rc")
            for result in run_results
            if isinstance(result, dict)
        }

        if statuses and statuses <= set(SYSCTL_MISSING_RCS):
            raise AnsibleActionFail(
                "The host has no sysctl to ask. It is not a POSIX"
                " interface and a host is under no obligation to have"
                " one"
            )
