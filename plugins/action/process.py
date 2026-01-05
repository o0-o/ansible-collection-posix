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

from ansible.errors import AnsibleActionFail, AnsibleConnectionFailure
from ansible.plugins.action import ActionBase
from ansible_collections.o0_o.posix.plugins.module_utils import (
    PosixActionBase,
    jc_parse,
    restructure_process,
)
from ansible_collections.o0_o.utils.plugins.module_utils import (
    truthy_or_string,
    wantlist,
)


class ActionModule(PosixActionBase, ActionBase):
    """Gather process information from POSIX systems.

    Uses ps command with jc parsing to provide structured process data.
    Supports filtering by PID or executable path.
    """

    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False
    _supports_diff = False

    def run(
        self, tmp: Any = None, task_vars: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Execute the process gathering action.

        :param Any tmp: Temporary directory (unused)
        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns dict[str, Any]: Result dict with process information
        """
        if task_vars is None:
            task_vars = {}

        result = super().run(task_vars=task_vars)
        del tmp  # Not used

        if result.get("skipped") or result.get("failed"):
            return result

        # Check mode - return empty results
        if self._task.check_mode:
            result["processes"] = []
            return result

        # Validate arguments
        argument_spec = {
            "pids": {
                "type": "list",
                "elements": "int",
                "aliases": ["pid"],
            },
            "executables": {
                "type": "list",
                "elements": "str",
                "aliases": ["executable"],
            },
            "raw": {"type": "raw", "default": "auto"},
        }

        validation_result, new_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )

        # Process raw parameter: accept boolean or 'auto'
        try:
            self.raw = truthy_or_string(new_args.pop("raw"), ["auto"])
        except ValueError as e:
            raise AnsibleActionFail(str(e)) from e

        # Normalize to lists using wantlist
        pids = wantlist(new_args.get("pids"))
        executables = wantlist(new_args.get("executables"))

        try:
            # Build ps command with all fields
            # Note: lstart is excluded because it contains spaces
            # which breaks jc parsing (jc can't tell where lstart
            # ends and command begins). We rely on etime for
            # elapsed time instead.
            ps_fields = [
                "pid",
                "ppid",
                "uid",
                "gid",
                "etime",
                "time",
                "stat",
                "pcpu",
                "pmem",
                "rss",
                "vsz",
                "command",
            ]

            # Build ps command
            # Use -ww for unlimited width (prevents command truncation)
            ps_cmd = ["ps", "-axww", "-o", ",".join(ps_fields)]

            # Execute ps command
            ps_result = self._command(ps_cmd, task_vars=task_vars)

            self._display.vvv(f"ps command returned rc={ps_result['rc']}")

            if ps_result["rc"] != 0:
                stderr = ps_result.get("stderr", "")
                result.update(
                    {
                        "failed": True,
                        "msg": f"ps command failed: {stderr}",
                        "processes": [],
                    }
                )
                return result

            # Parse with jc
            try:
                parsed_processes = jc_parse("ps", ps_result)
                self._display.vvv(
                    f"jc parsed {len(parsed_processes)} processes "
                    f"from ps output"
                )
            except Exception as e:
                result.update(
                    {
                        "failed": True,
                        "msg": f"Failed to parse ps output: {e}",
                        "processes": [],
                    }
                )
                return result

            # Filter processes based on pids/executables
            self._display.vvv(
                f"Filtering with pids={pids}, executables={executables}"
            )
            filtered_processes = self._filter_processes(
                parsed_processes, pids, executables
            )
            self._display.vvv(
                f"Filtered to {len(filtered_processes)} processes"
            )

            # Restructure each process with parsed/organized fields
            restructured_processes = []
            for proc in filtered_processes:
                restructured = restructure_process(proc)
                self._display.vvv(f"  Restructured process: {restructured}")
                restructured_processes.append(restructured)

            result["processes"] = restructured_processes
            result["changed"] = False

        except AnsibleConnectionFailure:
            raise
        except Exception as e:
            result.update(
                {
                    "failed": True,
                    "msg": f"Error gathering process information: {e}",
                    "processes": [],
                }
            )

        return result

    def _filter_processes(
        self,
        processes: list[dict[str, Any]],
        pids: Optional[list[int]],
        executables: Optional[list[str]],
    ) -> list[dict[str, Any]]:
        """Filter processes by PID or executable criteria.

        :param list[dict[str, Any]] processes: All processes from ps
        :param Optional[list[int]] pids: PIDs to filter for
        :param Optional[list[str]] executables: Executables to match
        :returns list[dict[str, Any]]: Filtered processes
        """
        # If no filters, return all
        if not pids and not executables:
            return processes

        filtered = []

        for proc in processes:
            pid = proc.get("pid")
            command = proc.get("command", "")

            # Check PID filter
            if pids and pid in pids:
                self._display.vvv(f"  Process {pid}: matched by PID")
                filtered.append(proc)
                continue

            # Check executable filter
            if executables and command:
                # Check if any requested executable appears in command
                # Don't try to parse command into executable/args since
                # processes can modify it via setproctitle()
                self._display.vvv(
                    f"  Process {pid}: command='{command[:80]}...'"
                )
                matched = False
                for req_exec in executables:
                    # Check if executable name appears in command
                    # (as word boundary to avoid partial matches)
                    if req_exec in command:
                        self._display.vvv(
                            f"    Matched: '{req_exec}' found in command"
                        )
                        filtered.append(proc)
                        matched = True
                        break
                if not matched:
                    self._display.vvv(
                        f"    No match: none of {executables} found "
                        f"in command"
                    )
            elif executables:
                self._display.vvv(
                    f"  Process {pid}: skipped (no command field)"
                )

        return filtered
