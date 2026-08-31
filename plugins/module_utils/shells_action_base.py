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

"""Base class for the action plugins that run a host's login shells.

Two plugins produce ``o0_shells`` by running shells - the gather and
the module named for the fact - and what they run is the whole of what
the fact means, so they plan it here rather than each their own way.
A shell fact is not read out of a file: it is what a login shell
turned out to do, and two producers planning that differently would
publish two answers to one question.
"""

from __future__ import annotations

from typing import Any, Optional

from ansible_collections.o0_o.posix.plugins.module_utils.read_posix_action_base import (  # noqa: E501
    ReadPosixActionBase,
)
from ansible_collections.o0_o.posix.plugins.module_utils.shells_utils import (
    SHELL_SYSTEM_HOME,
    compose_shells,
    get_shell_command_requests,
    get_shell_login_requests,
    process_shell_command_results,
)


class ShellsPosixActionBase(ReadPosixActionBase):
    """Plan and read back the observations of a host's login shells."""

    # The namespace that has a composer of its own
    PATHS_NAMESPACE = "o0_paths"

    # The namespace a passwd entry's shell and home are read from
    USERS_NAMESPACE = "o0_users"

    def _shell_probes(
        self,
        shell: str,
        known: dict[str, Any],
        uid: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """Plan the shell observations this run has reason to make.

        Two layers.  The system layer is the shell the task named, run
        out of the canonical home no host has, which is what a login
        shell does before any user's dot files enter into it.  The
        user layer is what a person actually gets when they log in.

        A run that can drop asks both out of a reset environment, and
        the difference is not cosmetic.  Run bare under become, the
        probe reports the environment sudo left it - a truncated PATH,
        the connection's working directory, the become target's mail
        spool - and files all of it as though it were the shell's.  A
        login su resets the environment to what the user really gets,
        so the system layer is forced to root and reads one canonical
        answer whoever the play became, and the user layer is asked of
        root and of the connecting user, each out of their own home,
        because those two are rarely configured alike.

        A dropped user-layer probe is not told which shell to run: the
        user's passwd entry decides and the answer says which it was.
        A run that cannot drop asks the effective user's own pair
        instead, named from the passwd entry, and reports whatever
        environment it was handed.

        A shell the path store has confirmed absent is not probed.
        The store is consulted rather than trusted for a positive: a
        path it has never been asked about is not a path known to be
        missing, and the probe answers that question itself.

        :param str shell: The shell the task named for the system
            layer
        :param dict[str, Any] known: What is already known, by
            namespace - the path store, and the users a passwd entry
            described
        :param Optional[int] uid: The effective uid, where one was
            determined
        :returns list[dict[str, Any]]: The probes to run
        """
        paths = known.get(self.PATHS_NAMESPACE) or {}

        def absent(path: str) -> bool:
            return path in paths and paths[path] is None

        identities = self._login_identities()
        dropper = identities[0] if identities else None

        requests: list[dict[str, Any]] = []

        if shell and not absent(shell):
            requests.extend(
                get_shell_command_requests(
                    [(shell, SHELL_SYSTEM_HOME)], dropper=dropper
                )
            )

        if identities:
            requests.extend(get_shell_login_requests(identities))
            return requests

        # Nothing to drop with, so the one login this run can observe
        # is the one it is already inside, named from the passwd entry
        # rather than answered by the probe
        entry = (known.get(self.USERS_NAMESPACE) or {}).get(str(uid)) or {}
        user_shell = entry.get("shell")
        user_home = entry.get("home")
        if (
            user_shell
            and user_home
            and not absent(user_shell)
            and (user_shell, user_home) != (shell, SHELL_SYSTEM_HOME)
        ):
            requests.extend(
                get_shell_command_requests([(user_shell, user_home)])
            )

        return requests

    def _composed_shells(
        self,
        run_results: list[dict[str, Any]],
        named: Optional[list[str]] = None,
    ) -> dict[str, dict[str, Any]]:
        """Read what the probes produced into the shells fact.

        :param list[dict[str, Any]] run_results: The batch's results,
            which may hold answers to questions besides these
        :param Optional[list[str]] named: The login shells the host
            names, as ``/etc/shells`` gave them
        :returns dict[str, dict[str, Any]]: The shells fact, empty
            where nothing was observed and nothing was named
        """
        probed, consulted = process_shell_command_results(run_results)

        return compose_shells(named, probed, consulted)
