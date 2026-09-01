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

from ansible_collections.o0_o.core.plugins.module_utils import (
    EVIDENCE,
    compose_evidence,
)
from ansible_collections.o0_o.posix.plugins.module_utils import (
    PosixActionBase,
    get_limits_command_requests,
    process_effective_uid_results,
    process_limits_command_results,
)

# What the inquiry consulted.  ulimit is a shell builtin and a builtin
# is a command a fact may name like any other; id is what says whose
# session answered.
LIMITS_COMMANDS = ("id", "ulimit")


class ActionModule(PosixActionBase, ActionBase):
    """Ask a session what it is limited to.

    An inquiry rather than a gather.  A resource limit belongs to one
    session, not to a host and not to a user: PAM sets a base at login
    and the shell's startup files adjust from there, so the answer is
    a property of the process that answered and of the path it was
    started through.

    Which is why this publishes no fact.  A fact outlives the task
    that gathered it and this answer does not outlive the session, so
    it comes back as a result and the play reads it where it asked.
    Whose session gets asked is the play's to choose: ``become`` and
    ``become_user`` select the identity, and asking twice as two
    identities is how two answers are had.
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
        """Ask the session this task runs in what it is limited to.

        :param Optional[str] tmp: Unused temporary directory path
        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns dict[str, Any]: Result with the limits under
            'limits' and the uid that answered under 'uid'
        """
        task_vars = task_vars or {}
        self._def_inventory_hostname(task_vars)

        result = super().run(tmp, task_vars=task_vars)
        del tmp  # unused

        result["invocation"] = self._task.args.copy()

        cmds = get_limits_command_requests()

        run_results = self._run(
            cmds,
            parallel=True,
            fail_fast=False,
            task_vars=task_vars,
            # Asking a shell what it is limited to changes nothing, and
            # a check mode run that skipped it would read as a session
            # with no limits
            check_mode=False,
        )

        fields, errors = process_limits_command_results(run_results)

        for err in errors:
            self._display.warning(f"[{self.inventory_hostname}] {err}")

        result.update(
            {
                "changed": False,
                # A session whose shell would not answer reports no
                # limits rather than none: the two are different, and
                # an empty mapping says the question was asked
                "limits": fields.get("limits") or {},
                "uid": process_effective_uid_results(run_results),
                EVIDENCE: compose_evidence(commands=LIMITS_COMMANDS),
            }
        )

        return result
