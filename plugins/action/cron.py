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
    PosixActionBase,
    compose_paths,
    name_origins,
)
from ansible_collections.o0_o.posix.plugins.module_utils.cron_utils import (
    FQCN,
    compose_cron_holdings,
    compose_cron_paths,
    compose_cron_users,
    cron_survey_answers,
    get_cron_read_requests,
    get_cron_survey_requests,
    spool_paths,
)


class ActionModule(PosixActionBase, ActionBase):
    """Report what a host is configured to run on a schedule.

    Two facts, because a crontab is two different things depending on
    where it sits.  The files a play could name - ``/etc/crontab`` and
    whatever is under ``/etc/cron.d`` - are files, so what they
    schedule is a fact about them and lands in ``o0_paths`` beside
    their bytes, the way ``/etc/fstab`` carries the filesystems it
    names.  A per-user crontab is a fact about the user who owns it
    and lands under their uid in ``o0_users``.

    Nothing is stored under a namespace of its own.  What a host runs
    on a schedule is those two answers joined, and joining them is the
    ``schedule`` lookup's business rather than a third copy's.

    Whose crontabs can be read depends on who is asking.  Any identity
    can read its own, which is the reading POSIX defines.  Reading
    somebody else's means reading the spool, which is root's to read,
    so a run that is not root reports itself and says nothing about
    anyone else - rather than reporting that nobody else has one.

    Every crontab read is held against the cron the host's kernel
    runs, and a job that cron would refuse is warned about by file or
    user, line and spelling.  The fact carries the job as written all
    the same: a warning is not an exclusion at the fact layer.
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
        """Ask the host what it schedules, and for whom.

        :param Optional[str] tmp: Unused temporary directory path
        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns dict[str, Any]: Result with the crontab files under
            'o0_paths', the per-user crontabs under 'o0_users', and
            ansible_facts where gather was asked for
        """
        task_vars = task_vars or {}
        self._def_inventory_hostname(task_vars)

        result = super().run(tmp, task_vars=task_vars)
        del tmp  # unused

        argument_spec = {
            "gather": {
                "type": "bool",
                "default": False,
            },
        }
        validation_result, new_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )
        result["invocation"] = self._task.args.copy()

        paths, users = self._survey(task_vars)

        facts: dict[str, Any] = {}
        if paths:
            facts["o0_paths"] = paths
        if users:
            facts["o0_users"] = users

        result.update(
            {
                "changed": False,
                "o0_paths": paths,
                "o0_users": users,
            }
        )

        if new_args.get("gather", False) and facts:
            result["ansible_facts"] = facts

        return result

    def _survey(
        self,
        task_vars: Optional[dict[str, Any]] = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Ask what schedules exist, then read what the asking named.

        Two round trips, and the second could not have ridden the
        first: every path and every name it reads is something the
        first had to answer with.

        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns tuple[dict[str, Any], dict[str, Any]]: The path
            entries and the user entries
        """
        surveyed = self._run(
            get_cron_survey_requests(),
            parallel=True,
            fail_fast=False,
            task_vars=task_vars,
            # Reading what a host schedules changes nothing, and a
            # check mode run that skipped it would read as a host that
            # schedules nothing
            check_mode=False,
        )

        answers = cron_survey_answers(surveyed)

        read = self._run(
            get_cron_read_requests(
                answers["dropins"],
                spool_paths(answers["holders"]),
                answers["holders"],
            ),
            parallel=True,
            fail_fast=False,
            task_vars=task_vars,
            check_mode=False,
        )

        held = compose_cron_holdings(answers, read)

        for err in held["errors"]:
            self._display.warning(f"[{self.inventory_hostname}] {err}")

        # A job the host's cron would refuse is warned about and
        # published as written: the fact says what the file says, and
        # leaving the job out is the schedule lookup's business
        for warning in held["warnings"]:
            self._display.warning(f"[{self.inventory_hostname}] {warning}")

        paths = compose_paths(
            None,
            compose_cron_paths(
                held["files"], answers["dropins"], held["there"]
            ),
            origin=FQCN,
        )

        return paths, name_origins(compose_cron_users(held["views"]), FQCN)
