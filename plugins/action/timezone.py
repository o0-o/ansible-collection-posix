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

import re
from typing import Any, Dict, List, Optional

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

        result.update(
            {
                "changed": False,
                "timezone": tz,
            }
        )
        return result

    def _get_timezone(
        self, task_vars: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Detect timezone using several POSIX-friendly techniques.

        :returns: dict with keys:
            name (optional), abbr (optional), source
        """
        # 1) Debian/Ubuntu: /etc/timezone file
        task_vars = task_vars or {}

        info: Dict[str, Any] = {}
        config: Dict[str, Any] = {}

        tz = self._from_etc_timezone(task_vars)
        self._merge_config(config, tz)
        if tz and tz.get("name"):
            info["name"] = tz["name"]

        localtime = self._from_localtime_symlink(task_vars)
        self._merge_config(config, localtime)
        if localtime and localtime.get("name") and "name" not in info:
            info["name"] = localtime["name"]

        if "name" not in info:
            tz = self._from_systemsetup(task_vars)
            self._merge_config(config, tz)
            if tz and tz.get("name"):
                info["name"] = tz["name"]

        if "name" not in info:
            tz = self._from_timedatectl(task_vars)
            self._merge_config(config, tz)
            if tz and tz.get("name"):
                info["name"] = tz["name"]

        if "name" not in info:
            fallback = self._from_date_abbr(task_vars)
            self._merge_config(config, fallback)
            if fallback:
                info.update(
                    {k: v for k, v in fallback.items() if k != "config"}
                )
                if config:
                    info["config"] = config
                return info
            raise RuntimeError("Timezone detection methods exhausted")

        info["zone"] = info["name"]

        zoneinfo_path = self._resolve_zoneinfo_path(
            info["name"], config, task_vars
        )
        if zoneinfo_path:
            posix_details = self._parse_zoneinfo(zoneinfo_path, task_vars)
            if posix_details:
                info.update(posix_details)
                config.setdefault(
                    "/etc/localtime",
                    {},
                ).setdefault("link", zoneinfo_path)

        info.update(self._active_time_info(task_vars))

        if config:
            info["config"] = config

        return info

    def _read_file(
        self, path: str, task_vars: Optional[Dict[str, Any]]
    ) -> Optional[str]:
        st = self._cmd(
            ["test", "-f", path], task_vars=task_vars, check_mode=False
        )
        if st.get("rc") != 0:
            return None
        cat = self._cmd(["cat", path], task_vars=task_vars, check_mode=False)
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
            return {
                "name": content,
                "config": {"/etc/timezone": {"path": "/etc/timezone"}},
            }
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
                return {
                    "name": name,
                    "config": {"/etc/localtime": {"link": target}},
                }
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
            offset_cmd = self._cmd(
                ["date", "+%z"], task_vars=task_vars, check_mode=False
            )
            result: Dict[str, Any] = {
                "abbr": abbr,
                "config": {"command": "date +%Z"},
            }
            if offset_cmd.get("rc") == 0:
                offset = (offset_cmd.get("stdout") or "").strip()
                if offset:
                    result["offset"] = offset
            return result
        return None

    def _merge_config(
        self,
        target: Dict[str, Any],
        source: Optional[Dict[str, Any]],
    ) -> None:
        if not source:
            return
        cfg = source.get("config")
        if not isinstance(cfg, dict):
            return
        for key, value in cfg.items():
            if (
                key in target
                and isinstance(target[key], dict)
                and isinstance(value, dict)
            ):
                target[key].update(value)
            else:
                target[key] = value

    def _resolve_zoneinfo_path(
        self,
        name: str,
        config: Dict[str, Dict[str, Any]],
        task_vars: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        localtime_entry = config.get("/etc/localtime")
        link = None
        if isinstance(localtime_entry, dict):
            link = localtime_entry.get("link")
        if link and self._path_exists(link, task_vars):
            return link

        candidate = f"/usr/share/zoneinfo/{name}"
        if self._path_exists(candidate, task_vars):
            return candidate
        return None

    def _path_exists(
        self, candidate: str, task_vars: Optional[Dict[str, Any]]
    ) -> bool:
        result = self._cmd(
            ["test", "-f", candidate], task_vars=task_vars, check_mode=False
        )
        return result.get("rc") == 0

    def _parse_zoneinfo(
        self, path: str, task_vars: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        candidate = self._read_posix_candidate(
            ["strings", "-n", "1", path], task_vars
        )
        if candidate is None:
            candidate = self._read_posix_candidate(
                ["tail", "-c", "512", path], task_vars
            )
        if candidate is None:
            return {}

        details = self._parse_posix_string(candidate)
        details["posix"] = candidate
        return details

    def _read_posix_candidate(
        self,
        command: List[str],
        task_vars: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        result = self._cmd(command, task_vars=task_vars, check_mode=False)
        if result.get("rc") != 0:
            return None
        stdout = (result.get("stdout") or "").replace("\x00", "\n")
        for line in stdout.splitlines():
            candidate = line.strip()
            if not candidate or candidate.startswith("TZif"):
                continue
            if re.match(r"^[A-Za-z]{3,}[-+]?[0-9]", candidate):
                return candidate
        return None

    def _parse_posix_string(self, value: str) -> Dict[str, Any]:
        pattern = re.compile(
            r"^(?P<std>[A-Za-z]{3,})"
            r"(?P<std_offset>[-+]?\d+(?::\d{2}(?::\d{2})?)?)"
            r"(?:"
            r"(?P<dst>[A-Za-z]{3,})"
            r"(?P<dst_offset>[-+]?\d+(?::\d{2}(?::\d{2})?)?)?"
            r",(?P<start>[^,]+),(?P<end>[^,]+)"
            r")?"
            r"$"
        )
        match = pattern.match(value)
        if not match:
            return {}

        info: Dict[str, Any] = {}

        std_offset_spec = match.group("std_offset")
        std_seconds = self._posix_seconds(std_offset_spec)
        info["standard"] = {
            "abbr": match.group("std"),
            "offset": self._format_offset_from_seconds(std_seconds),
        }

        dst_code = match.group("dst")
        if dst_code:
            dst_offset_spec = match.group("dst_offset")
            if dst_offset_spec:
                dst_seconds = self._posix_seconds(dst_offset_spec)
            else:
                dst_seconds = std_seconds - 3600
            daylight: Dict[str, Any] = {
                "abbr": dst_code,
                "offset": self._format_offset_from_seconds(dst_seconds),
            }
            start_rule = match.group("start")
            end_rule = match.group("end")
            if start_rule:
                daylight["start"] = self._parse_transition_rule(start_rule)
            if end_rule:
                daylight["end"] = self._parse_transition_rule(end_rule)
            info["daylight"] = daylight

        return info

    def _posix_seconds(self, spec: str) -> int:
        sign = 1
        if spec.startswith("-"):
            sign = -1
            spec = spec[1:]
        elif spec.startswith("+"):
            spec = spec[1:]
        parts = spec.split(":")
        hours = int(parts[0]) if parts[0] else 0
        minutes = int(parts[1]) if len(parts) > 1 else 0
        seconds = int(parts[2]) if len(parts) > 2 else 0
        return sign * (hours * 3600 + minutes * 60 + seconds)

    def _format_offset_from_seconds(self, seconds: int) -> str:
        adjusted = -seconds
        sign = "+" if adjusted >= 0 else "-"
        adjusted = abs(adjusted)
        hours = adjusted // 3600
        minutes = (adjusted % 3600) // 60
        secs = adjusted % 60
        if secs:
            return f"{sign}{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{sign}{hours:02d}:{minutes:02d}"

    def _parse_transition_rule(self, rule: str) -> Dict[str, Any]:
        time_part = "02:00"
        if "/" in rule:
            rule, time_spec = rule.split("/", 1)
            time_part = self._format_rule_time(time_spec)
        else:
            time_part = "02:00"

        if rule.startswith("M"):
            parts = rule[1:].split(".")
            if len(parts) == 3 and all(part.isdigit() for part in parts):
                return {
                    "month": int(parts[0]),
                    "week": int(parts[1]),
                    "weekday": int(parts[2]),
                    "time": time_part,
                }
        return {"time": time_part}

    def _format_rule_time(self, spec: str) -> str:
        if not spec:
            return "02:00"
        sign = ""
        if spec.startswith("-"):
            sign = "-"
            spec = spec[1:]
        elif spec.startswith("+"):
            spec = spec[1:]
        parts = spec.split(":")
        hours = int(parts[0]) if parts and parts[0] else 0
        minutes = int(parts[1]) if len(parts) > 1 else 0
        seconds = int(parts[2]) if len(parts) > 2 else 0
        if seconds:
            return f"{sign}{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{sign}{hours:02d}:{minutes:02d}"

    def _active_time_info(
        self, task_vars: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {}

        abbr_cmd = self._cmd(
            ["date", "+%Z"], task_vars=task_vars, check_mode=False
        )
        if abbr_cmd.get("rc") == 0:
            abbr = (abbr_cmd.get("stdout") or "").strip()
            if abbr:
                result["abbr"] = abbr

        offset_cmd = self._cmd(
            ["date", "+%z"], task_vars=task_vars, check_mode=False
        )
        if offset_cmd.get("rc") == 0:
            offset = (offset_cmd.get("stdout") or "").strip()
            if offset:
                result["offset"] = offset

        return result
