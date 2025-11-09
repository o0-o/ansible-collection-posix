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

import shlex
from typing import Any, Dict, List, Optional

from ansible.module_utils.common.text.converters import to_bytes, to_text
from ansible.plugins.action import ActionBase

from ansible_collections.o0_o.posix.plugins.module_utils import PosixActionBase
from ansible_collections.o0_o.posix.plugins.module_utils import format_command

__metaclass__ = type


class ActionModule(PosixActionBase, ActionBase):
    """
    Execute multiple commands in a single SSH round trip.

    Batches commands into one shell script that captures each
    command's rc/stdout/stderr and returns them with length prefixes
    for accurate parsing.
    """

    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False

    def _parse_batch_output(
        self, output: str, num_commands: int
    ) -> List[Dict[str, Any]]:
        """
        Parse length-prefixed batch output.

        :param str output: Raw batch output string
        :param int num_commands: Expected number of commands
        :returns List[Dict[str, Any]]: Parsed command results
        """
        results = []

        # Convert to bytes for accurate length counting
        # Use to_bytes() with surrogate_or_strict for round-trip safety
        output_bytes = to_bytes(output, errors="surrogate_or_strict")
        offset = 0

        for i in range(num_commands):
            try:
                # Read RC line
                rc_line_end = output_bytes.find(b"\n", offset)
                rc_line = to_text(
                    output_bytes[offset:rc_line_end],
                    errors="surrogate_or_strict",
                )
                rc = int(rc_line.strip())
                offset = rc_line_end + 1

                # Read stdout length line (format: "42 /path/file")
                stdout_len_end = output_bytes.find(b"\n", offset)
                stdout_len_line = to_text(
                    output_bytes[offset:stdout_len_end],
                    errors="surrogate_or_strict",
                )
                stdout_len = int(stdout_len_line.strip().split()[0])
                offset = stdout_len_end + 1

                # Read exactly stdout_len bytes
                stdout_bytes = output_bytes[offset : offset + stdout_len]
                stdout = to_text(stdout_bytes, errors="surrogate_or_strict")
                offset += stdout_len

                # Read stderr length line (format: "28 /path/file")
                stderr_len_end = output_bytes.find(b"\n", offset)
                stderr_len_line = to_text(
                    output_bytes[offset:stderr_len_end],
                    errors="surrogate_or_strict",
                )
                stderr_len = int(stderr_len_line.strip().split()[0])
                offset = stderr_len_end + 1

                # Read exactly stderr_len bytes
                stderr_bytes = output_bytes[offset : offset + stderr_len]
                stderr = to_text(stderr_bytes, errors="surrogate_or_strict")
                offset += stderr_len

                results.append(
                    {
                        "rc": rc,
                        "stdout": stdout,
                        "stderr": stderr,
                        "stdout_lines": stdout.splitlines() if stdout else [],
                        "stderr_lines": stderr.splitlines() if stderr else [],
                    }
                )

            except (ValueError, IndexError) as e:
                results.append(
                    {
                        "msg": f"Failed to parse output for command {i}: {e}",
                        "rc": None,
                        "stdout": "",
                        "stderr": "",
                    }
                )
                break

        return results

    def _build_batch_script(self, tmp: str) -> str:
        """
        Build the batched shell script using Ansible's tmpdir.

        :param str tmp: Temporary directory path
        :returns str: Shell script content
        """
        lines = [
            "set +e",  # Don't exit on command errors
            "",
        ]

        for i, cmd in enumerate(commands):
            cmd_str = format_command(cmd)

            if chdir:
                cmd_str = f"(cd {shlex.quote(chdir)} && {cmd_str})"

            lines.extend(
                [
                    # Execute and capture
                    f'({cmd_str}) 1>"{tmpdir}/{i}.stdout" 2>"{tmpdir}/{i}.stderr"',  # noqa: E501
                    f"RC_{i}=$?",
                ]
            )

            if fail_fast:
                lines.append(f"[ $RC_{i} -eq 0 ] || exit $RC_{i}")

            lines.extend(
                [
                    # Output: RC, stdout_length, stdout, stderr_length, stderr
                    f'echo "$RC_{i}"',
                    f'wc -c "{tmpdir}/{i}.stdout"',
                    f'cat "{tmpdir}/{i}.stdout"',
                    f'wc -c "{tmpdir}/{i}.stderr"',
                    f'cat "{tmpdir}/{i}.stderr"',
                    "",
                ]
            )

        return "\n".join(lines)

    def _def_args(self) -> Dict[str, Any]:
        """
        Parse and validate module arguments.

        :returns dict: The validated argument dictionary
        """
        argument_spec = {
            "commands": {
                "type": "list",
                "elements": "raw",  # Accept str or list
                "required": True,
            },
            "chdir": {"type": "path"},
            "fail_fast": {"type": "bool", "default": False},
            "_force_raw": {"type": "bool", "default": False},
        }

        validation_result, new_module_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )
        self.commands = new_module_args["commands"]
        self.chdir = new_module_args["chdir"]
        self.fail_fast = new_module_args["fail_fast"]
        self.force_raw = new_module_args["_force_raw"]

        return new_module_args

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute multiple commands in batch.

        :param Optional[str] tmp: Temporary directory path
        :param Optional[Dict[str, Any]] task_vars: Task variables
        :returns Dict[str, Any]: Ansible result dictionary
        """
        task_vars = task_vars or {}
        self.host = self._get_inventory_hostname(task_vars)

        new_module_args = self._def_args()

        self.result = super(ActionModule, self).run(tmp, task_vars=task_vars)

        # Get or create Ansible's temporary directory
        if tmp is None or tmp == "":
            tmp = self._make_tmp_path()

        # Build batched script using Ansible's tmpdir
        script = self._build_batch_script(tmp)

        # Execute single batch command
        cmd_result = self._cmd(script, task_vars=task_vars)

        if cmd_result.get("failed"):
            result.update(cmd_result)
            return result

        # Parse combined output back into individual results
        try:
            parsed_results = self._parse_batch_output(
                output=cmd_result["stdout"],
                num_commands=len(commands),
            )
        except Exception as e:
            result["failed"] = True
            result["msg"] = f"Failed to parse batch output: {e}"
            result["raw_output"] = cmd_result["stdout"]
            return result

        # Check if any command failed
        any_failed = any(
            r.get("rc") is None or r.get("rc") != 0 for r in parsed_results
        )

        result.update(
            {
                "changed": True,
                "failed": any_failed,
                "results": parsed_results,
                "msg": f"Executed {len(commands)} commands",
            }
        )

        return result
