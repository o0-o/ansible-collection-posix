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
from ansible.errors import AnsibleActionFail

from ansible_collections.o0_o.posix.plugins.module_utils import PosixActionBase


class ActionModule(PosixActionBase, ActionBase):
    """Detect the system locale on POSIX systems.

    Collects locale category values from the ``locale`` utility when
    available, falling back to the process environment.
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
        """Execute locale detection and return structured results.

        :param Optional[str] tmp: Unused temporary directory path
        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns dict[str, Any]: Result with locale categories under
            'locale' key
        :raises AnsibleActionFail: When locale detection fails
            completely
        """

        task_vars = task_vars or {}
        tmp = None

        result = super().run(task_vars=task_vars)

        try:
            data = self._get_locale(task_vars=task_vars)
        except Exception as e:
            host = self._get_inventory_hostname(task_vars)
            self._display.warning(
                f"[{host}] Failed to detect locale: {type(e).__name__}: {e}"
            )
            raise AnsibleActionFail(f"Failed to detect locale: {e}")

        result.update(
            {
                "changed": False,
                "locale": data,
            }
        )
        return result

    def _parse_assignments(self, text: Optional[str]) -> dict[str, str]:
        """Parse KEY=VALUE lines into a dictionary.

        :param Optional[str] text: Text containing KEY=VALUE lines
        :returns dict[str, str]: Mapping of keys to values with quotes
            stripped
        """

        data: dict[str, str] = {}
        for line in (text or "").splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"')
            if key:
                data[key] = value
        return data

    def _env_from_locale(
        self, task_vars: Optional[dict[str, Any]]
    ) -> dict[str, str]:
        """Collect locale variables from ``locale`` command output.

        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns dict[str, str]: Environment variables from locale
            command
        """

        lc = self._command(["locale"], task_vars=task_vars, check_mode=False)
        if lc.get("rc") != 0:
            return {}
        return self._parse_assignments(lc.get("stdout"))

    def _env_from_environment(
        self, task_vars: Optional[dict[str, Any]]
    ) -> dict[str, str]:
        """Collect locale variables from the environment.

        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns dict[str, str]: Environment variables from env command
        """

        env_cmd = self._command(["env"], task_vars=task_vars, check_mode=False)
        if env_cmd.get("rc") != 0:
            return {}
        return self._parse_assignments(env_cmd.get("stdout"))

    def _get_locale(
        self, task_vars: Optional[dict[str, Any]]
    ) -> dict[str, Any]:
        """Build locale categories from command or environment data.

        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns dict[str, Any]: Locale categories mapped from
            environment vars
        :raises RuntimeError: When no locale information can be obtained
        """

        data = self._env_from_locale(task_vars)
        if not data:
            data = self._env_from_environment(task_vars)
        if not data:
            raise RuntimeError("Locale detection methods exhausted")

        mapping = {
            "language": "LANG",
            "all": "LC_ALL",
            "characters": "LC_CTYPE",
            "collation": "LC_COLLATE",
            "messages": "LC_MESSAGES",
            "monetary": "LC_MONETARY",
            "numeric": "LC_NUMERIC",
            "time": "LC_TIME",
        }

        result = {key: None for key in mapping}
        for key, env_key in mapping.items():
            value = data.get(env_key)
            if value:
                result[key] = value
        return result
