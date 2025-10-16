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

from typing import Any, Dict, List, Optional

from ansible.errors import AnsibleConnectionFailure
from ansible.plugins.action import ActionBase
from ansible_collections.o0_o.posix.plugins.module_utils import (
    PosixActionBase,
    jc_parse,
    restructure_process,
)
from ansible_collections.o0_o.utils.plugins.module_utils import (
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
        self, tmp: Any = None, task_vars: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute the process gathering action.

        :param Any tmp: Temporary directory (unused)
        :param Optional[Dict[str, Any]] task_vars: Task variables
        :returns Dict[str, Any]: Result dict with process information
        """
        if task_vars is None:
            task_vars = {}

        result = super().run(tmp, task_vars)
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
        }

        validation_result, new_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )

        # Normalize to lists using wantlist
        pids = wantlist(new_args.get("pids"))
        executables = wantlist(new_args.get("executables"))

        try:
            # Build ps command with all fields
            ps_fields = [
                "pid",
                "ppid",
                "uid",
                "gid",
                "etime",
                "time",
                "lstart",
                "pcpu",
                "pmem",
                "rss",
                "vsz",
                "command",
            ]

            # Build ps command
            ps_cmd = ["ps", "-ax", "-o", ",".join(ps_fields)]

            # Execute ps command
            ps_result = self._cmd(ps_cmd, task_vars=task_vars)

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
            filtered_processes = self._filter_processes(
                parsed_processes, pids, executables
            )

            # Restructure each process with parsed/organized fields
            restructured_processes = []
            for proc in filtered_processes:
                restructured = restructure_process(proc)
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
        processes: List[Dict[str, Any]],
        pids: Optional[List[int]],
        executables: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        """Filter processes based on PID or executable criteria.

        :param List[Dict[str, Any]] processes: All processes from ps
        :param Optional[List[int]] pids: PIDs to filter for
        :param Optional[List[str]] executables: Executables to filter for
        :returns List[Dict[str, Any]]: Filtered processes
        """
        # If no filters, return all
        if not pids and not executables:
            return processes

        filtered = []

        for proc in processes:
            # Check PID filter
            if pids and proc.get("pid") in pids:
                filtered.append(proc)
                continue

            # Check executable filter
            if executables and proc.get("command"):
                # Extract executable from command (first word)
                cmd_parts = str(proc["command"]).split()
                if cmd_parts:
                    executable = cmd_parts[0]
                    # Match exact path or basename
                    if executable in executables:
                        filtered.append(proc)
                        continue
                    # Also check basename match
                    basename = executable.split("/")[-1]
                    if basename in executables:
                        filtered.append(proc)
                        continue
                    # Check if any requested executable is in the full path
                    for req_exec in executables:
                        if req_exec in executable:
                            filtered.append(proc)
                            break

        return filtered
