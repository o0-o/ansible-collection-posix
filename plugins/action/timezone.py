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
from ansible_collections.o0_o.utils.plugins.module_utils import (
    truthy_or_string,
)

from ansible_collections.o0_o.posix.plugins.module_utils import (
    PosixActionBase,
    parse_posix_tz,
    parse_etc_timezone,
    parse_localtime_symlink,
    parse_systemsetup_output,
    parse_timedatectl_output,
    parse_date_abbr,
    parse_posix_candidate,
    merge_timezone_config,
)


class ActionModule(PosixActionBase, ActionBase):
    """Detect the IANA timezone name on POSIX systems.

    This action plugin detects the configured timezone on remote POSIX
    systems using multiple portable detection methods. It tries various
    approaches to maximize compatibility across different operating
    systems including Linux, macOS, and BSD variants.

    Detection methods (in order of preference):
    - /etc/timezone file (Debian/Ubuntu systems)
    - /etc/localtime symlink target (most POSIX systems)
    - systemsetup -gettimezone command (macOS)
    - timedatectl show command (systemd-based systems)
    - date command output (universal fallback)

    The plugin also attempts to extract detailed POSIX timezone
    information including daylight saving time transition rules when
    available from zoneinfo files.

    Returns comprehensive timezone information including the IANA
    timezone name, current abbreviation, UTC offset, and detection
    method configuration details.
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
        """Execute timezone detection.

        :param Optional[str] tmp: Temporary directory path (unused)
        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns dict[str, Any]: Result with timezone information
        """
        task_vars = task_vars or {}
        self._def_inventory_hostname(task_vars)

        result = super().run(task_vars=task_vars)
        del tmp  # unused

        # Validate arguments (primarily for raw execution support)
        argument_spec = {
            "raw": {"type": "raw", "default": "auto"},
        }
        validation_result, new_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )

        # Process raw parameter: accept boolean or 'auto'
        try:
            raw = truthy_or_string(new_args.pop("raw"), ["auto"])
        except ValueError as e:
            raise AnsibleActionFail(str(e)) from e

        try:
            tz = self._get_timezone(task_vars=task_vars)
        except Exception as e:
            raise AnsibleActionFail(f"Failed to detect timezone: {e}") from e

        result.update(
            {
                "changed": False,
                "timezone": tz,
            }
        )
        return result

    def _get_timezone(
        self, task_vars: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Detect timezone using several POSIX-friendly techniques.

        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns dict[str, Any]: Timezone info with name, zone, config,
            and optional POSIX details
        """
        task_vars = task_vars or {}

        info: dict[str, Any] = {}
        config: dict[str, Any] = {}

        # Try /etc/timezone file
        tz = self._from_etc_timezone(task_vars)
        merge_timezone_config(config, tz)
        if tz and tz.get("name"):
            info["name"] = tz["name"]

        # Try /etc/localtime symlink
        if "name" not in info:
            localtime = self._from_localtime_symlink(task_vars)
            merge_timezone_config(config, localtime)
            if localtime and localtime.get("name"):
                info["name"] = localtime["name"]

        # Try macOS systemsetup command
        if "name" not in info:
            tz = self._from_systemsetup(task_vars)
            merge_timezone_config(config, tz)
            if tz and tz.get("name"):
                info["name"] = tz["name"]

        # Try systemd timedatectl
        if "name" not in info:
            tz = self._from_timedatectl(task_vars)
            merge_timezone_config(config, tz)
            if tz and tz.get("name"):
                info["name"] = tz["name"]

        # Fallback to date abbreviation
        if "name" not in info:
            fallback = self._from_date_abbr(task_vars)
            merge_timezone_config(config, fallback)
            if fallback:
                info.update(
                    {k: v for k, v in fallback.items() if k != "config"}
                )
                if config:
                    info["config"] = config
                return info
            raise RuntimeError("Timezone detection methods exhausted")

        # Set zone to match name
        info["zone"] = info["name"]

        # Try to get POSIX timezone string details
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

        # Add current time info
        info.update(self._active_time_info(task_vars))

        if config:
            info["config"] = config

        return info

    def _read_file(
        self, path: str, task_vars: Optional[dict[str, Any]]
    ) -> Optional[str]:
        """Read file contents if file exists.

        :param str path: File path to read
        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns Optional[str]: File contents, or None if not found
        """
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
        self, task_vars: Optional[dict[str, Any]]
    ) -> Optional[dict[str, Any]]:
        """Detect timezone from /etc/timezone file.

        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns Optional[dict[str, Any]]: Timezone info or None
        """
        content = self._read_file("/etc/timezone", task_vars)
        if not content:
            return None
        return parse_etc_timezone(content)

    def _from_localtime_symlink(
        self, task_vars: Optional[dict[str, Any]]
    ) -> Optional[dict[str, Any]]:
        """Detect timezone from /etc/localtime symlink.

        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns Optional[dict[str, Any]]: Timezone info or None
        """
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
        return parse_localtime_symlink(target)

    def _from_systemsetup(
        self, task_vars: Optional[dict[str, Any]]
    ) -> Optional[dict[str, Any]]:
        """Detect timezone from macOS systemsetup command.

        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns Optional[dict[str, Any]]: Timezone info or None
        """
        ss = self._cmd(
            ["systemsetup", "-gettimezone"],
            task_vars=task_vars,
            check_mode=False,
        )
        if ss.get("rc") != 0:
            return None
        out = (ss.get("stdout") or "").strip()
        return parse_systemsetup_output(out)

    def _from_timedatectl(
        self, task_vars: Optional[dict[str, Any]]
    ) -> Optional[dict[str, Any]]:
        """Detect timezone from timedatectl command.

        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns Optional[dict[str, Any]]: Timezone info or None
        """
        td = self._cmd(
            ["timedatectl", "show", "-p", "Timezone", "--value"],
            task_vars=task_vars,
            check_mode=False,
        )
        if td.get("rc") != 0:
            return None
        out = (td.get("stdout") or "").strip()
        return parse_timedatectl_output(out)

    def _from_date_abbr(
        self, task_vars: Optional[dict[str, Any]]
    ) -> Optional[dict[str, Any]]:
        """Get timezone abbreviation and offset from date command.

        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns Optional[dict[str, Any]]: Timezone info or None
        """
        date = self._cmd(
            ["date", "+%Z"], task_vars=task_vars, check_mode=False
        )
        if date.get("rc") != 0:
            return None
        abbr = (date.get("stdout") or "").strip()
        if not abbr:
            return None

        offset_cmd = self._cmd(
            ["date", "+%z"], task_vars=task_vars, check_mode=False
        )
        offset = None
        if offset_cmd.get("rc") == 0:
            offset = (offset_cmd.get("stdout") or "").strip()

        return parse_date_abbr(abbr, offset)

    def _resolve_zoneinfo_path(
        self,
        name: str,
        config: dict[str, dict[str, Any]],
        task_vars: Optional[dict[str, Any]],
    ) -> Optional[str]:
        """Find path to zoneinfo file for timezone name.

        :param str name: Timezone name like "America/New_York"
        :param dict[str, dict[str, Any]] config: Config with possible link
        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns Optional[str]: Path to zoneinfo file, or None
        """
        # Check if we already have a link from /etc/localtime
        localtime_entry = config.get("/etc/localtime")
        link = None
        if isinstance(localtime_entry, dict):
            link = localtime_entry.get("link")
        if link and self._path_exists(link, task_vars):
            return link

        # Try standard zoneinfo location
        candidate = f"/usr/share/zoneinfo/{name}"
        if self._path_exists(candidate, task_vars):
            return candidate
        return None

    def _path_exists(
        self, candidate: str, task_vars: Optional[dict[str, Any]]
    ) -> bool:
        """Check if path exists.

        :param str candidate: Path to check
        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns bool: True if path exists
        """
        result = self._cmd(
            ["test", "-f", candidate], task_vars=task_vars, check_mode=False
        )
        return result.get("rc") == 0

    def _parse_zoneinfo(
        self, path: str, task_vars: Optional[dict[str, Any]]
    ) -> dict[str, Any]:
        """Extract POSIX timezone details from zoneinfo file.

        :param str path: Path to zoneinfo file
        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns dict[str, Any]: Parsed POSIX timezone info
        """
        # Try strings command
        candidate = self._read_posix_candidate(
            ["strings", "-n", "1", path], task_vars
        )
        if candidate is None:
            # Try tail fallback
            candidate = self._read_posix_candidate(
                ["tail", "-c", "512", path], task_vars
            )
        if candidate is None:
            return {}

        details = parse_posix_tz(candidate)
        details["posix"] = candidate
        return details

    def _read_posix_candidate(
        self,
        command: list[str],
        task_vars: Optional[dict[str, Any]],
    ) -> Optional[str]:
        """Execute command and extract POSIX timezone string.

        :param list[str] command: Command to execute
        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns Optional[str]: POSIX timezone string, or None
        """
        result = self._cmd(command, task_vars=task_vars, check_mode=False)
        if result.get("rc") != 0:
            return None
        stdout = result.get("stdout") or ""
        return parse_posix_candidate(stdout)

    def _active_time_info(
        self, task_vars: Optional[dict[str, Any]]
    ) -> dict[str, Any]:
        """Get current timezone abbreviation and offset.

        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns dict[str, Any]: Dict with abbr and offset keys
        """
        result: dict[str, Any] = {}

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
