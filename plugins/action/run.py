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

from ansible.module_utils.common.text.converters import to_bytes, to_text
from ansible.plugins.action import ActionBase

from ansible_collections.o0_o.posix.plugins.module_utils import PosixActionBase

__metaclass__ = type


class ActionModule(PosixActionBase, ActionBase):
    """
    Execute multiple commands in a single SSH round trip.

    Batches commands into one shell script that captures each
    command's rc/stdout/stderr and returns them with length prefixes
    for accurate parsing. Commands run in parallel by default using
    background jobs (&) and wait for efficiency.
    """

    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False

    def _parse_batch_output(self, output: str) -> None:
        """
        Parse length-prefixed batch output.

        :param str output: Raw batch output string
        """
        self.result["commands"] = []

        # Convert to bytes for accurate length counting
        # Use to_bytes() with surrogate_or_strict for round-trip safety
        output_bytes = to_bytes(output, errors="surrogate_or_strict")
        offset = 0

        for i, cmd in enumerate(self.commands):
            command_result = {
                "cmd": cmd,
                "rc": None,
                "stdout": None,
                "stderr": None,
            }

            try:
                # Read RC line
                rc_line_end = output_bytes.find(b"\n", offset)
                if rc_line_end == -1:
                    raise ValueError("Newline not found when searching for rc")
                rc_line = to_text(
                    output_bytes[offset:rc_line_end],
                    errors="surrogate_or_strict",
                )
                command_result["rc"] = int(rc_line.strip())
                offset = rc_line_end + 1

                # Read stdout length line (format: "42 /path/file")
                stdout_len_end = output_bytes.find(b"\n", offset)
                if stdout_len_end == -1:
                    raise ValueError(
                        "Newline not found when searching for stdout"
                    )
                stdout_len_line = to_text(
                    output_bytes[offset:stdout_len_end],
                    errors="surrogate_or_strict",
                )
                # Handle both \n and \r\n line endings
                parts = stdout_len_line.strip().split()
                if not parts:
                    raise ValueError(
                        f"Empty wc output line for stdout: "
                        f"{repr(stdout_len_line)}"
                    )
                stdout_len = int(parts[0])
                offset = stdout_len_end + 1

                # Read exactly stdout_len bytes
                stdout_bytes = output_bytes[offset : offset + stdout_len]
                stdout = to_text(stdout_bytes, errors="surrogate_or_strict")
                if self.strip:
                    stdout = stdout.rstrip()
                command_result["stdout"] = stdout
                command_result["stdout_lines"] = (
                    stdout.splitlines() if stdout else []
                )
                offset += stdout_len

                # Read stderr length line (format: "28 /path/file")
                stderr_len_end = output_bytes.find(b"\n", offset)
                if stderr_len_end == -1:
                    raise ValueError(
                        "Newline not found when searching for stderr"
                    )
                stderr_len_line = to_text(
                    output_bytes[offset:stderr_len_end],
                    errors="surrogate_or_strict",
                )
                # Handle both \n and \r\n line endings
                parts = stderr_len_line.strip().split()
                if not parts:
                    raise ValueError(
                        f"Empty wc output line for stderr: "
                        f"{repr(stderr_len_line)}"
                    )
                stderr_len = int(parts[0])
                offset = stderr_len_end + 1

                # Read exactly stderr_len bytes
                stderr_bytes = output_bytes[offset : offset + stderr_len]
                stderr = to_text(stderr_bytes, errors="surrogate_or_strict")
                if self.strip:
                    stderr = stderr.rstrip()
                command_result["stderr"] = stderr
                command_result["stderr_lines"] = (
                    stderr.splitlines() if stderr else []
                )
                offset += stderr_len

            except (ValueError, IndexError) as e:
                command_result["msg"] = (
                    f"Failed to parse output for command: {e}"
                )
                raise e

            finally:
                self.result["commands"].append(command_result)

        return

    def _build_batch_script(self, tmp: str) -> str:
        """
        Build the batched shell script using Ansible's tmp.

        :param str tmp: Temporary directory path
        :returns str: Shell script content
        """
        if self.fail_fast:
            cmds = ["set -e"]  # Exit on command errors
        else:
            cmds = ["set +e"]  # Don't exit on command errors

        if self.parallel:
            # Launch all commands in background
            for i, cmd in enumerate(self.commands):
                if not isinstance(cmd, str):
                    cmd = self._format_command(cmd)
                cmds.append(
                    f'({cmd}) 1>"{tmp}{i}.stdout" 2>"{tmp}{i}.stderr" & '
                    f"pid{i}=$!"
                )

            # Wait for each and collect results
            for i in range(len(self.commands)):
                cmds.extend(
                    [
                        f'wait "$pid{i}"',
                        'echo "$?"',
                        f'wc -c "{tmp}{i}.stdout"',
                        f'cat "{tmp}{i}.stdout"',
                        f'wc -c "{tmp}{i}.stderr"',
                        f'cat "{tmp}{i}.stderr"',
                    ]
                )
        else:
            # Sequential execution
            for i, cmd in enumerate(self.commands):
                if not isinstance(cmd, str):
                    cmd = self._format_command(cmd)
                cmds.extend(
                    [
                        # Execute and capture
                        f'({cmd}) 1>"{tmp}{i}.stdout" 2>"{tmp}{i}.stderr"',
                        'echo "${?}"',
                        f'wc -c "{tmp}{i}.stdout"',
                        f'cat "{tmp}{i}.stdout"',
                        f'wc -c "{tmp}{i}.stderr"',
                        f'cat "{tmp}{i}.stderr"',
                    ]
                )

        # Ensure script ends with a newline for proper parsing
        cmds.append("echo")

        return "; ".join(cmds)

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
            "parallel": {"type": "bool", "default": True},
            "fail_fast": {"type": "bool", "default": False},
            "strip": {"type": "bool", "default": True},
            "_force_raw": {"type": "bool", "default": False},
        }

        validation_result, new_module_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )
        self.commands = new_module_args["commands"]
        self.chdir = new_module_args["chdir"]
        self.parallel = new_module_args["parallel"]
        self.fail_fast = new_module_args["fail_fast"]
        self.strip = new_module_args["strip"]
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
        self._def_inventory_hostname(task_vars)

        self._def_args()

        self.result = super(ActionModule, self).run(tmp, task_vars=task_vars)
        self.result["invocation"] = self._task.args.copy()

        # Get or create Ansible's temporary directory
        if tmp is None or tmp == "":
            tmp = self._make_tmp_path()

        # Build batched script using Ansible's tmp
        script = self._build_batch_script(tmp)
        self._display.vvv(f"Batch command:\n{script}")

        # Execute single batch command
        # strip=False to preserve length-prefix format parsing
        cmd_result = self._cmd(
            script,
            chdir=self.chdir,
            strip=False,
            check_mode=self._task.check_mode,
            task_vars=task_vars,
        )
        self._display.vvv(f"Batch result:\n{to_text(cmd_result)}")

        self.result.update(
            {
                "failed": cmd_result.get("failed", False),
                "raw": cmd_result["raw"],
                "stderr": cmd_result["stderr"],
                "start": cmd_result.get("start"),
                "end": cmd_result.get("end"),
                "delta": cmd_result.get("delta"),
            }
        )

        # Parse combined output back into individual results
        try:
            self._parse_batch_output(
                output=cmd_result["stdout"],
            )
        except Exception as e:
            self.result.update(
                {
                    "failed": True,
                    "msg": f"Failed to parse batch output: {e}",
                    "stdout": cmd_result["stdout"],
                }
            )
            return self.result

        # Check if any command failed
        any_failed = any(
            r.get("rc") is None or r.get("rc") != 0
            for r in self.result["commands"]
        )

        self.result.update(
            {
                "changed": True,
                "failed": any_failed,
                "msg": f"Executed {len(self.commands)} commands",
            }
        )

        return self.result
