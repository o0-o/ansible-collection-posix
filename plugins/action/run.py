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

import time
from typing import Any, Optional, Union

from ansible.errors import AnsibleActionFail
from ansible.module_utils.common.text.converters import to_bytes, to_text
from ansible.plugins.action import ActionBase
from ansible_collections.o0_o.utils.plugins.module_utils import (
    format_elapsed_seconds,
    format_epoch_timestamp,
    truthy_or_string,
)
from ansible_collections.o0_o.posix.plugins.module_utils import (
    PosixActionBase,
    format_command,
)


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

    def _parse_batch_output(
        self,
        output: str,
        command_requests: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Parse length-prefixed batch output into command results.

        Parses the structured output format produced by _build_batch_script.
        Each command's output block contains:
        - Return code line
        - Start timestamp line (epoch seconds)
        - End timestamp line (epoch seconds)
        - Stdout length line (format: "N /path/to/file")
        - Stdout content (exactly N bytes)
        - Stderr length line (format: "N /path/to/file")
        - Stderr content (exactly N bytes)

        The original request dict is merged with the result, preserving any
        metadata (implementation, type, parser, validator, etc.) from
        process_command_spec output.

        :param str output: Raw batch output string from shell execution
        :param list[dict[str, Any]] command_requests: Command request dicts
            that were executed. Each is merged with its result.
        :returns list[dict[str, Any]]: List of result dicts, each containing
            the original request keys plus 'rc', 'stdout', 'stderr',
            'stdout_lines', 'stderr_lines', and 'elapsed' keys
        :raises ValueError: If output format is malformed or incomplete
        """
        results = []

        # Convert to bytes for accurate length counting
        # Use to_bytes() with surrogate_or_strict for round-trip safety
        output_bytes = to_bytes(output, errors="surrogate_or_strict")

        # Skip any leading whitespace/newlines
        offset = 0
        while offset < len(output_bytes) and output_bytes[
            offset : offset + 1
        ] in (b"\n", b"\r", b" ", b"\t"):
            offset += 1

        for i, request in enumerate(command_requests):
            # Start with defaults, will be overwritten by parsed values.
            # Request values take precedence via update() in finally block.
            command_result = {
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
                rc_str = rc_line.strip()
                if not rc_str:
                    raise ValueError(f"Empty RC line for command {i}")
                command_result["rc"] = int(rc_str)
                offset = rc_line_end + 1

                # Read start time line
                start_time_end = output_bytes.find(b"\n", offset)
                if start_time_end == -1:
                    raise ValueError(
                        "Newline not found when searching for start time"
                    )
                start_time_line = to_text(
                    output_bytes[offset:start_time_end],
                    errors="surrogate_or_strict",
                )
                start_time = int(start_time_line.strip())
                offset = start_time_end + 1

                # Read end time line
                end_time_end = output_bytes.find(b"\n", offset)
                if end_time_end == -1:
                    raise ValueError(
                        "Newline not found when searching for end time"
                    )
                end_time_line = to_text(
                    output_bytes[offset:end_time_end],
                    errors="surrogate_or_strict",
                )
                end_time = int(end_time_line.strip())
                offset = end_time_end + 1

                # Calculate elapsed time
                elapsed_seconds = end_time - start_time
                command_result["elapsed"] = format_elapsed_seconds(
                    elapsed_seconds
                )

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
                # Merge with original request, giving request precedence.
                # This allows users to override rc, stderr, etc. and
                # preserves metadata (implementation, type, parser, etc.)
                command_result.update(request)
                results.append(command_result)

        return results

    def _build_command_wrapper(
        self,
        cmd: str,
        tmp: str,
        index: int,
        non_error_codes: list[int],
    ) -> str:
        """Build a shell wrapper that executes a command with rc checking.

        Creates a subshell wrapper that:
        - Disables errexit locally to capture rc regardless of exit status
        - Runs the command and captures stdout/stderr to files
        - Saves the real rc to file for reporting
        - Exits 0 if rc is in non_error_codes, else exits 1

        This allows fail_fast (set -e) to respect non_error_codes.

        :param str cmd: The command string to execute
        :param str tmp: Temporary directory path prefix
        :param int index: Command index for file naming
        :param list[int] non_error_codes: Return codes to treat as success
        :returns str: Shell wrapper command string
        """
        pattern = "|".join(str(c) for c in non_error_codes)
        return (
            f'( set +e; ({cmd}) 1>"{tmp}{index}.stdout" '
            f'2>"{tmp}{index}.stderr"; __rc=$?; '
            f'echo $__rc >"{tmp}{index}.rc"; '
            f'case $__rc in {pattern}) exit 0;; *) exit 1;; esac )'
        )

    def _build_batch_script(
        self,
        command_requests: list[dict[str, Any]],
        tmp: str,
    ) -> str:
        """Build a shell script that executes commands and captures output.

        Generates a POSIX-compatible shell script that:
        - Executes each command in a subshell
        - Captures stdout/stderr to temporary files
        - Records start/end timestamps for timing
        - Outputs results in length-prefixed format for parsing
        - Respects non_error_codes for each command

        The script respects self.parallel and self.fail_fast settings.
        In parallel mode, commands run as background jobs. In sequential
        mode with fail_fast, the script exits on first failure (respecting
        each command's non_error_codes).

        :param list[dict[str, Any]] command_requests: Command request dicts,
            each with a 'command' key containing string or list
        :param str tmp: Temporary directory path prefix for output files
        :returns str: Complete shell script as a single string
        """
        if self.fail_fast:
            cmds = ["set -e"]  # Exit on command errors
        else:
            cmds = ["set +e"]  # Don't exit on command errors

        # Remove aliases to ensure consistent command behavior
        cmds.append("unalias -a 2>/dev/null || :")

        if self.parallel:
            # Launch all commands in background with timing
            # Write RC to file to avoid stdout interleaving
            for i, request in enumerate(command_requests):
                cmd = request["command"]
                if not isinstance(cmd, str):
                    cmd = format_command(cmd)
                non_error_codes = request.get("non_error_codes", [0])
                wrapper = self._build_command_wrapper(
                    cmd, tmp, i, non_error_codes
                )
                cmds.append(
                    f'(date +%s >"{tmp}{i}.start"; '
                    f'{wrapper}; '
                    f'date +%s >"{tmp}{i}.end") & '
                    f"pid{i}=$!"
                )

            # Wait for each and collect results
            for i in range(len(command_requests)):
                cmds.extend(
                    [
                        f'wait "$pid{i}"',
                        f'cat "{tmp}{i}.rc"',
                        f'cat "{tmp}{i}.start"',
                        f'cat "{tmp}{i}.end"',
                        f'wc -c "{tmp}{i}.stdout"',
                        f'cat "{tmp}{i}.stdout"',
                        f'wc -c "{tmp}{i}.stderr"',
                        f'cat "{tmp}{i}.stderr"',
                    ]
                )
        else:
            # Sequential execution with timing
            for i, request in enumerate(command_requests):
                cmd = request["command"]
                if not isinstance(cmd, str):
                    cmd = format_command(cmd)
                non_error_codes = request.get("non_error_codes", [0])
                wrapper = self._build_command_wrapper(
                    cmd, tmp, i, non_error_codes
                )
                cmds.extend(
                    [
                        f'date +%s >"{tmp}{i}.start"',
                        wrapper,
                        f'date +%s >"{tmp}{i}.end"',
                        f'cat "{tmp}{i}.rc"',
                        f'cat "{tmp}{i}.start"',
                        f'cat "{tmp}{i}.end"',
                        f'wc -c "{tmp}{i}.stdout"',
                        f'cat "{tmp}{i}.stdout"',
                        f'wc -c "{tmp}{i}.stderr"',
                        f'cat "{tmp}{i}.stderr"',
                    ]
                )

        # Ensure script ends with a newline for proper parsing
        cmds.append("echo")

        # Use newlines instead of semicolons for ksh compatibility.
        # OpenBSD's pdksh fails to capture PIDs from background jobs when
        # commands are semicolon-separated (e.g., "cmd & pid=$!; wait $pid"
        # results in "wait: argument must be %job or process id").
        # Newline separation works correctly on both bash and ksh.
        script = "\n".join(cmds)
        return script

    def _estimate_script_length(
        self,
        command_requests: list[dict[str, Any]],
        tmp: str,
    ) -> int:
        """Estimate the byte length of a batch script for given commands.

        Builds the actual script and returns twice its length as a safety
        margin to account for shell escaping and JSON serialization overhead
        during transmission.

        Used by _split_commands_by_length to determine when to split
        commands into multiple batches to avoid exceeding shell limits.

        :param list[dict[str, Any]] command_requests: Command request dicts
        :param str tmp: Temporary directory path prefix
        :returns int: Estimated script length in bytes (2x actual length)
        """
        script = self._build_batch_script(command_requests, tmp)

        # Multiply by 2 for safety margin (shell escaping, JSON overhead)
        return len(script) * 2

    def _split_commands_by_length(
        self,
        max_length: int = 65536,  # 64 KB default
        max_count: int = 63,  # Max commands per batch
    ) -> list[list[dict[str, Any]]]:
        """Split self.command_requests into batches respecting size/count.

        Iterates through self.command_requests and groups them into batches
        where each batch's estimated script length stays under max_length
        and the command count stays under max_count. This prevents shell
        command-line length limits from being exceeded.

        :param int max_length: Maximum estimated script length in bytes.
            Defaults to 64KB which is safe for most systems
        :param int max_count: Maximum commands per batch. Defaults to 63
            to stay under typical shell job limits for parallel execution
        :returns list[list[dict[str, Any]]]: List of request batches,
            where each batch is a list of command request dicts
        """
        batches = []
        current_batch = []
        tmp_estimate = "/tmp/ansible_tmp"  # Placeholder for estimation

        for request in self.command_requests:
            test_batch = current_batch + [request]
            estimated_len = self._estimate_script_length(
                test_batch, tmp_estimate
            )

            # Check both size and count limits
            if current_batch and (
                estimated_len > max_length or len(test_batch) > max_count
            ):
                # Current batch would exceed limit, save it and start new
                batches.append(current_batch)
                current_batch = [request]
            else:
                current_batch.append(request)

        if current_batch:
            batches.append(current_batch)

        return batches

    def _execute_batch(
        self,
        batch_requests: list[dict[str, Any]],
        tmp: str,
        task_vars: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Execute a single batch of commands and return results.

        :param list[dict[str, Any]] batch_requests: Command request dicts
            to execute in this batch
        :param str tmp: Temporary directory path
        :param dict task_vars: Task variables
        :returns list[dict[str, Any]]: List of result dicts (merged with
            original request dicts)
        """
        # Build batched script
        script = self._build_batch_script(batch_requests, tmp)
        self._display.vvv(f"Batch command:\n{script}")

        # Execute batch
        cmd_result = self._command(
            script,
            chdir=self.chdir,
            strip=False,
            check_mode=self._task.check_mode,
            task_vars=task_vars,
            raw=self.raw,
        )

        if cmd_result.get("failed"):
            error_msg = cmd_result.get("msg", "Unknown error")
            raise AnsibleActionFail(f"Batch execution failed: {error_msg}")

        # Parse output and return results (merged with request dicts)
        return self._parse_batch_output(cmd_result["stdout"], batch_requests)

    def _is_command_failed(self, result: dict[str, Any]) -> bool:
        """Check if a command result indicates failure.

        Uses non_error_codes from the result dict if present, otherwise
        treats only rc=0 as success. This allows command specs to define
        acceptable non-zero return codes.

        :param dict[str, Any] result: Command result dict with 'rc' key
            and optional 'non_error_codes' key
        :returns bool: True if the command failed, False otherwise
        """
        rc = result.get("rc")
        if rc is None:
            return True
        non_error_codes = result.get("non_error_codes", [0])
        return rc not in non_error_codes

    def _normalize_command_request(
        self, item: Union[str, list, dict[str, Any]]
    ) -> dict[str, Any]:
        """Normalize a command item to a command request dict.

        Accepts strings, lists (argv), or dicts with a 'command' key.
        Returns a dict with at least a 'command' key. Dict inputs are
        returned as-is (preserving metadata like implementation, type,
        parser, validator from process_command_spec output).

        :param Union[str, list, dict[str, Any]] item: Command item to
            normalize. Can be a command string, argv list, or request dict
        :returns dict[str, Any]: Command request dict with 'command' key
        :raises AnsibleActionFail: If dict input lacks 'command' key
        """
        if isinstance(item, dict):
            if "command" not in item:
                raise AnsibleActionFail(
                    "Command dict must contain a 'command' key. "
                    f"Got keys: {list(item.keys())}"
                )
            return item.copy()  # Copy to avoid mutating original
        return {"command": item}

    def _def_args(self) -> None:
        """Parse and validate module arguments."""
        argument_spec = {
            "commands": {
                "type": "raw",  # Accept list or dict
                "required": True,
            },
            "chdir": {"type": "path"},
            "parallel": {"type": "bool"},  # Default derived from fail_fast
            "fail_fast": {"type": "bool", "default": False},
            "strip": {"type": "bool", "default": True},
            "raw": {"type": "raw", "default": "auto"},
        }

        validation_result, new_module_args = self.validate_argument_spec(
            argument_spec=argument_spec,
        )

        # Extract and normalize command requests
        commands_input = new_module_args["commands"]
        self.is_dict_mode = isinstance(commands_input, dict)
        if self.is_dict_mode:
            self.command_keys = list(commands_input.keys())
            # Normalize each value to a request dict (preserves metadata)
            self.command_requests = [
                self._normalize_command_request(v)
                for v in commands_input.values()
            ]
        else:
            self.command_keys = None
            # Normalize each item to a request dict
            self.command_requests = [
                self._normalize_command_request(c) for c in commands_input
            ]

        # Set instance variables from validated args
        self.chdir = new_module_args["chdir"]
        self.fail_fast = new_module_args["fail_fast"]
        self.strip = new_module_args["strip"]

        # Derive parallel from fail_fast if not explicitly set
        parallel = new_module_args["parallel"]
        if parallel is None:
            self.parallel = not self.fail_fast
        else:
            self.parallel = parallel
            # Validate: can't have parallel=true AND fail_fast=true
            if self.parallel and self.fail_fast:
                raise AnsibleActionFail(
                    "Cannot use parallel=true with fail_fast=true. "
                    "fail_fast only works with sequential execution."
                )

        # Process raw parameter: accept boolean or 'auto'
        try:
            self.raw = truthy_or_string(new_module_args["raw"], ["auto"])
        except ValueError as e:
            raise AnsibleActionFail(str(e)) from e

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Execute multiple commands in batch with automatic
        command-length-aware batching.

        :param Optional[str] tmp: Temporary directory path
        :param Optional[dict[str, Any]] task_vars: Task variables
        :returns dict[str, Any]: Ansible result dictionary
        """
        task_vars = task_vars or {}
        self._def_inventory_hostname(task_vars)

        self._def_args()

        self.result = super(ActionModule, self).run(task_vars=task_vars)
        self.result["invocation"] = self._task.args.copy()

        # Ensure tmp is a valid path for remote temporary files
        tmp = self._make_tmp_path()
        self._display.vvv(f"Temp path: {tmp}")

        try:
            # Check mode: validate we could run, but don't actually execute
            if self._task.check_mode:
                self.result.update(
                    {
                        "changed": False,
                        "skipped": True,
                        "msg": "Check mode: batch execution skipped",
                    }
                )
                return self.result

            # Capture start time
            start_time = time.time()
            # Check if we need to split into multiple batches
            max_command_length = 65536  # 64 KB safe default
            max_command_count = 63  # Safe limit for parallel execution
            estimated_length = self._estimate_script_length(
                self.command_requests, tmp
            )

            if (
                estimated_length > max_command_length
                or len(self.command_requests) >= max_command_count
            ):
                # Split commands into batches
                request_batches = self._split_commands_by_length(
                    max_command_length, max_command_count
                )
                num_batches = len(request_batches)

                # Determine which threshold triggered batching
                reasons = []
                if len(self.command_requests) >= max_command_count:
                    reasons.append(
                        f"command count {len(self.command_requests)} >= "
                        f"{max_command_count}"
                    )
                if estimated_length > max_command_length:
                    reasons.append(
                        f"length {estimated_length} > {max_command_length}"
                    )

                self._display.vvv(
                    f"Batching triggered ({', '.join(reasons)}), "
                    f"splitting into {num_batches} batches"
                )

                # Execute all batches and collect results
                all_results = []
                for i, batch in enumerate(request_batches, 1):
                    self._display.vvv(
                        f"Executing batch {i}/{num_batches} "
                        f"({len(batch)} commands)"
                    )
                    batch_results = self._execute_batch(batch, tmp, task_vars)
                    all_results.extend(batch_results)

                self.result["commands"] = all_results
            else:
                # Single batch execution
                num_batches = 1
                self.result["commands"] = self._execute_batch(
                    self.command_requests, tmp, task_vars
                )

            # Convert to dict if dict mode
            if self.is_dict_mode:
                command_results = self.result["commands"]
                self.result["commands"] = dict(
                    zip(self.command_keys, command_results)
                )

            # Check if any command failed (respects non_error_codes)
            command_results = (
                self.result["commands"].values()
                if self.is_dict_mode
                else self.result["commands"]
            )
            any_failed = any(
                self._is_command_failed(r) for r in command_results
            )

            # Capture end time and calculate elapsed
            end_time = time.time()
            elapsed_seconds = int(end_time - start_time)

            # Build message with batch count
            batch_suffix = (
                f" in {num_batches} batches" if num_batches > 1 else ""
            )
            cmd_count = len(self.command_requests)
            result_msg = f"Executed {cmd_count} commands{batch_suffix}"
            self.result.update(
                {
                    "changed": True,
                    "failed": any_failed,
                    "msg": result_msg,
                    "count": cmd_count,
                    "batches": num_batches,
                    "started": format_epoch_timestamp(start_time),
                    "ended": format_epoch_timestamp(end_time),
                    "elapsed": format_elapsed_seconds(elapsed_seconds),
                    "raw": self.raw is True,
                }
            )

            return self.result

        except AnsibleActionFail:
            raise
        except Exception as e:
            # Capture end time even on failure
            end_time = time.time()
            elapsed_seconds = int(end_time - start_time)
            self.result.update(
                {
                    "failed": True,
                    "msg": f"Batch execution error: {e}",
                    "started": format_epoch_timestamp(start_time),
                    "ended": format_epoch_timestamp(end_time),
                    "elapsed": format_elapsed_seconds(elapsed_seconds),
                    "raw": self.raw is True,
                }
            )
            return self.result
        finally:
            # Clean up remote temporary files
            self._remove_tmp_path(tmp)
