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

from typing import Any, Dict, Optional

from ansible.plugins.action import ActionBase
from ansible.errors import AnsibleActionFail

from ansible_collections.o0_o.posix.plugins.module_utils import (
    PosixActionBase,
)


class ActionModule(PosixActionBase, ActionBase):
    """Detect the IANA timezone name on POSIX systems.

    Tries multiple portable approaches across Linux, macOS, and *BSD:
    - /etc/timezone file (Debian/Ubuntu)
    - /etc/localtime symlink target (most POSIX, including macOS/*BSD)
    - systemsetup -gettimezone (macOS)
    - timedatectl show -p Timezone --value (systemd)
    Falls back to the timezone abbreviation from date +%Z when needed.
    """

    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False
    _supports_diff = False

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        task_vars = task_vars or {}
        tmp = None

        result = super().run(tmp, task_vars)

        try:
            tz = self._get_timezone(task_vars=task_vars)
        except Exception as e:
            host = self._get_inventory_hostname(task_vars)
            self._display.warning(
                f"[{host}] Failed to detect timezone: "
                f"{type(e).__name__}: {e}"
            )
            raise AnsibleActionFail(f"Failed to detect timezone: {e}")

        result.update({
            "changed": False,
            "timezone": tz,
        })
        return result

    def _get_timezone(
        self, task_vars: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Detect timezone using several POSIX-friendly techniques.

        :returns: dict with keys:
            name (optional), abbr (optional), source
        """
        # 1) Debian/Ubuntu: /etc/timezone file
        tz = self._from_etc_timezone(task_vars)
        if tz:
            return tz

        # 2) Symlink target of /etc/localtime
        tz = self._from_localtime_symlink(task_vars)
        if tz:
            return tz

        # 3) macOS: systemsetup -gettimezone
        tz = self._from_systemsetup(task_vars)
        if tz:
            return tz

        # 4) systemd: timedatectl
        tz = self._from_timedatectl(task_vars)
        if tz:
            return tz

        # 5) Fallback: abbreviation
        tz = self._from_date_abbr(task_vars)
        if tz:
            return tz

        raise RuntimeError("Timezone detection methods exhausted")

    def _read_file(
        self, path: str, task_vars: Optional[Dict[str, Any]]
    ) -> Optional[str]:
        st = self._cmd(
            ["test", "-f", path], task_vars=task_vars, check_mode=False
        )
        if st.get("rc") != 0:
            return None
        cat = self._cmd(
            ["cat", path], task_vars=task_vars, check_mode=False
        )
        if cat.get("rc") != 0:
            return None
        return (cat.get("stdout") or "").strip()

    def _from_etc_timezone(
        self, task_vars: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        content = self._read_file("/etc/timezone", task_vars)
        if not content:
            return None
        # Validate simple Region/City form
        if "/" in content and all(part for part in content.split("/")):
            return {"name": content, "config": {"path": "/etc/timezone"}}
        return None

    def _from_localtime_symlink(
        self, task_vars: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        # Try readlink first
        rl = self._cmd(
            ["readlink", "/etc/localtime"],
            task_vars=task_vars,
            check_mode=False,
        )
        target = None
        if rl.get("rc") == 0:
            target = (rl.get("stdout") or "").strip()
        else:
            # Fallback to ls -l parsing
            ls = self._cmd(
                ["ls", "-l", "/etc/localtime"],
                task_vars=task_vars,
                check_mode=False,
            )
            if ls.get("rc") == 0:
                out = ls.get("stdout") or ""
                arrow = " -> "
                if arrow in out:
                    target = out.split(arrow, 1)[1].strip()
        if not target:
            return None
        # Extract portion after zoneinfo/
        key = "/zoneinfo/"
        if key in target:
            name = target.split(key, 1)[1]
            if name:
                return {"name": name, "config": {"path": "/etc/localtime"}}
        return None

    def _from_systemsetup(
        self, task_vars: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        # macOS systemsetup -gettimezone
        ss = self._cmd(
            ["systemsetup", "-gettimezone"],
            task_vars=task_vars,
            check_mode=False,
        )
        if ss.get("rc") != 0:
            return None
        out = (ss.get("stdout") or "").strip()
        # Expected: "Time Zone: America/Los_Angeles"
        if ":" in out:
            val = out.split(":", 1)[1].strip()
            if "/" in val:
                return {
                    "name": val,
                    "config": {"command": "systemsetup -gettimezone"},
                }
        return None

    def _from_timedatectl(
        self, task_vars: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        td = self._cmd(
            ["timedatectl", "show", "-p", "Timezone", "--value"],
            task_vars=task_vars,
            check_mode=False,
        )
        if td.get("rc") != 0:
            return None
        out = (td.get("stdout") or "").strip()
        if "/" in out:
            return {
                "name": out,
                "config": {
                    "command": "timedatectl show -p Timezone --value",
                },
            }
        return None

    def _from_date_abbr(
        self, task_vars: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        date = self._cmd(
            ["date", "+%Z"], task_vars=task_vars, check_mode=False
        )
        if date.get("rc") != 0:
            return None
        abbr = (date.get("stdout") or "").strip()
        if abbr:
            return {"abbr": abbr, "config": {"command": "date +%Z"}}
        return None
