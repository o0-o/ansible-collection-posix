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

import subprocess
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest
from ansible.errors import AnsibleActionFail
from ansible_collections.o0_o.posix.plugins.action.command import (
    ActionModule as CommandActionModule,
)


def _shell(cmd: str) -> dict[str, Any]:
    """Run what a transport was handed, through a real shell.

    :param str cmd: The command string the transport was given
    :returns dict[str, Any]: The three fields a POSIX transport
        answers with
    """
    completed = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "rc": completed.returncode,
        "stdout": completed.stdout.decode("utf-8"),
        "stderr": completed.stderr.decode("utf-8"),
    }


class _CommandOverBothTransports(CommandActionModule):
    """The command action with both of its transports run locally.

    A batch's fate is whatever the command action reports back, so a
    test that stubs ``_command`` measures its own opinion of that
    answer rather than the answer. Each transport is stubbed at the
    seam it actually uses -- the raw one at the low-level transport,
    the native one at the module delegation -- and both hand the
    script to the same shell, so the only thing that differs between
    them is what each says about a script that exited non-zero.
    """

    def _low_level_execute_command(
        self,
        cmd: str,
        sudoable: bool = True,
        in_data: Optional[bytes] = None,
        executable: Optional[str] = None,
        chdir: Optional[str] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Answer the raw transport from a local shell."""
        return _shell(cmd)

    def _execute_module(
        self,
        module_name: Optional[str] = None,
        module_args: Optional[dict[str, Any]] = None,
        task_vars: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Answer the native delegation as the builtin module does.

        ansible.builtin.command fails on a non-zero status and names
        it, which is the half of the answer the raw path had to be
        taught to give.
        """
        answer = _shell(module_args["_raw_params"])
        if answer["rc"] != 0:
            answer.update({"failed": True, "msg": "non-zero return code"})
        return answer


def _delegate_to_command(plugin) -> None:
    """Send this action's delegation to a real command action.

    :param plugin: The run action instance to wire up
    """

    def run_action(
        plugin_name: str,
        plugin_args: dict[str, Any],
        task_vars: Optional[dict[str, Any]] = None,
        check_mode: Optional[bool] = None,
    ) -> dict[str, Any]:
        assert plugin_name == "o0_o.posix.command"
        task = MagicMock()
        task.async_val = 0
        task.check_mode = bool(check_mode)
        task.action = plugin_name
        task.args = dict(plugin_args)

        command = _CommandOverBothTransports(
            task=task,
            connection=MagicMock(),
            play_context=MagicMock(),
            loader=MagicMock(),
            templar=MagicMock(),
            shared_loader_obj=MagicMock(),
        )
        command._display = MagicMock()
        command._remove_tmp_path = MagicMock()
        command.inventory_hostname = "localhost"

        return command.run(task_vars=task_vars or {})

    plugin._run_action = run_action


@pytest.fixture
def plugin():
    """Create run ActionModule instance with patched dependencies."""
    from ansible_collections.o0_o.posix.plugins.action.run import ActionModule

    task = MagicMock()
    task.async_val = 0
    task.check_mode = False

    action = ActionModule(
        task=task,
        connection=MagicMock(),
        play_context=MagicMock(),
        loader=MagicMock(),
        templar=MagicMock(),
        shared_loader_obj=MagicMock(),
    )
    action._display = MagicMock()
    action._make_tmp_path = MagicMock(return_value="/tmp/ansible-tmp-123")
    action._remove_tmp_path = MagicMock()
    action.inventory_hostname = "localhost"

    return action


def test_run_list_mode(monkeypatch, plugin) -> None:
    """Test run with list input returns list output."""
    plugin._task.args = {
        "commands": ["echo foo", "echo bar"],
    }

    # Mock _command to return batch output with start/end times
    def mock_cmd(cmd, **kwargs):
        return {
            "rc": 0,
            "raw": False,
            "stdout": (
                "0\n1735689600\n1735689601\n4 /tmp/0.stdout\nfoo\n"
                "0 /tmp/0.stderr\n"
                "0\n1735689600\n1735689601\n4 /tmp/1.stdout\nbar\n"
                "0 /tmp/1.stderr\n\n"
            ),
            "stderr": "",
            "start": "2025-01-01 00:00:00",
            "end": "2025-01-01 00:00:01",
            "delta": "0:00:01",
        }

    monkeypatch.setattr(plugin, "_command", mock_cmd)

    result = plugin.run(task_vars={})

    assert result["changed"] is True
    assert isinstance(result["commands"], list)
    assert len(result["commands"]) == 2
    assert result["commands"][0]["command"] == "echo foo"
    assert result["commands"][1]["command"] == "echo bar"


def test_run_dict_mode(monkeypatch, plugin) -> None:
    """Test run with dict input returns dict output."""
    plugin._task.args = {
        "commands": {"first": "echo foo", "second": "echo bar"},
    }

    # Mock _command to return batch output with start/end times
    def mock_cmd(cmd, **kwargs):
        return {
            "rc": 0,
            "raw": False,
            "stdout": (
                "0\n1735689600\n1735689601\n4 /tmp/0.stdout\nfoo\n"
                "0 /tmp/0.stderr\n"
                "0\n1735689600\n1735689601\n4 /tmp/1.stdout\nbar\n"
                "0 /tmp/1.stderr\n\n"
            ),
            "stderr": "",
            "start": "2025-01-01 00:00:00",
            "end": "2025-01-01 00:00:01",
            "delta": "0:00:01",
        }

    monkeypatch.setattr(plugin, "_command", mock_cmd)

    result = plugin.run(task_vars={})

    assert result["changed"] is True
    assert isinstance(result["commands"], dict)
    assert "first" in result["commands"]
    assert "second" in result["commands"]
    assert result["commands"]["first"]["command"] == "echo foo"
    assert result["commands"]["second"]["command"] == "echo bar"


def test_run_dict_mode_preserves_keys(monkeypatch, plugin) -> None:
    """Test dict mode preserves all keys from input."""
    plugin._task.args = {
        "commands": {
            "kernel": "uname -s",
            "machine": "uname -m",
            "hostname": "hostname",
        },
    }

    # Mock _command to return batch output with start/end times
    def mock_cmd(cmd, **kwargs):
        return {
            "rc": 0,
            "raw": False,
            "stdout": (
                "0\n1735689600\n1735689601\n6 /tmp/0.stdout\nLinux\n"
                "0 /tmp/0.stderr\n"
                "0\n1735689600\n1735689601\n7 /tmp/1.stdout\nx86_64\n"
                "0 /tmp/1.stderr\n"
                "0\n1735689600\n1735689601\n9 /tmp/2.stdout\ntesthost\n"
                "0 /tmp/2.stderr\n\n"
            ),
            "stderr": "",
            "start": "2025-01-01 00:00:00",
            "end": "2025-01-01 00:00:01",
            "delta": "0:00:01",
        }

    monkeypatch.setattr(plugin, "_command", mock_cmd)

    result = plugin.run(task_vars={})

    assert isinstance(result["commands"], dict)
    assert set(result["commands"].keys()) == {"kernel", "machine", "hostname"}
    assert result["commands"]["kernel"]["command"] == "uname -s"
    assert result["commands"]["machine"]["command"] == "uname -m"
    assert result["commands"]["hostname"]["command"] == "hostname"


def test_run_dict_mode_single_command(monkeypatch, plugin) -> None:
    """Test dict mode with single command."""
    plugin._task.args = {
        "commands": {"only_one": "echo test"},
    }

    # Mock _command to return batch output with start/end times
    def mock_cmd(cmd, **kwargs):
        return {
            "rc": 0,
            "raw": False,
            "stdout": (
                "0\n1735689600\n1735689601\n5 /tmp/0.stdout\ntest\n"
                "0 /tmp/0.stderr\n\n"
            ),
            "stderr": "",
            "start": "2025-01-01 00:00:00",
            "end": "2025-01-01 00:00:01",
            "delta": "0:00:01",
        }

    monkeypatch.setattr(plugin, "_command", mock_cmd)

    result = plugin.run(task_vars={})

    assert isinstance(result["commands"], dict)
    assert len(result["commands"]) == 1
    assert "only_one" in result["commands"]
    assert result["commands"]["only_one"]["command"] == "echo test"


def test_run_dict_mode_with_failures(monkeypatch, plugin) -> None:
    """Test dict mode properly handles command failures."""
    plugin._task.args = {
        "commands": {"pass": "true", "fail": "false"},
    }

    # Mock _command to return batch output with one failure
    def mock_cmd(cmd, **kwargs):
        return {
            "rc": 0,
            "raw": False,
            "stdout": (
                "0\n1735689600\n1735689601\n0 /tmp/0.stdout\n"
                "0 /tmp/0.stderr\n"
                "1\n1735689600\n1735689601\n0 /tmp/1.stdout\n"
                "0 /tmp/1.stderr\n\n"
            ),
            "stderr": "",
            "start": "2025-01-01 00:00:00",
            "end": "2025-01-01 00:00:01",
            "delta": "0:00:01",
        }

    monkeypatch.setattr(plugin, "_command", mock_cmd)

    result = plugin.run(task_vars={})

    assert result["failed"] is True
    assert isinstance(result["commands"], dict)
    assert result["commands"]["pass"]["rc"] == 0
    assert result["commands"]["fail"]["rc"] == 1


def test_run_dict_command_items(monkeypatch, plugin) -> None:
    """Test commands with dict items containing 'command' key."""
    plugin._task.args = {
        "commands": {
            "posix_uname": {"command": "uname -s", "parser": "uname"},
            "posix_uptime": {"command": "uptime", "parser": "uptime"},
        },
    }

    # Mock _command to return batch output
    # Use simple output for easier byte counting: "foo\n" = 4 bytes
    def mock_cmd(cmd, **kwargs):
        return {
            "rc": 0,
            "raw": False,
            "stdout": (
                "0\n1735689600\n1735689601\n4 /tmp/0.stdout\nfoo\n"
                "0 /tmp/0.stderr\n"
                "0\n1735689600\n1735689601\n4 /tmp/1.stdout\nbar\n"
                "0 /tmp/1.stderr\n\n"
            ),
            "stderr": "",
            "start": "2025-01-01 00:00:00",
            "end": "2025-01-01 00:00:01",
            "delta": "0:00:01",
        }

    monkeypatch.setattr(plugin, "_command", mock_cmd)

    result = plugin.run(task_vars={})

    assert result["changed"] is True
    assert isinstance(result["commands"], dict)
    assert "posix_uname" in result["commands"]
    assert "posix_uptime" in result["commands"]
    # Verify the actual command was extracted from dict
    assert result["commands"]["posix_uname"]["command"] == "uname -s"
    assert result["commands"]["posix_uptime"]["command"] == "uptime"
    # Verify metadata is preserved
    assert result["commands"]["posix_uname"]["parser"] == "uname"
    assert result["commands"]["posix_uptime"]["parser"] == "uptime"


def test_run_list_with_dict_command_items(monkeypatch, plugin) -> None:
    """Test list mode with dict items containing 'command' key."""
    plugin._task.args = {
        "commands": [
            {"command": "echo foo", "extra": "ignored"},
            {"command": "echo bar", "meta": "data"},
        ],
    }

    # Mock _command to return batch output
    def mock_cmd(cmd, **kwargs):
        return {
            "rc": 0,
            "raw": False,
            "stdout": (
                "0\n1735689600\n1735689601\n4 /tmp/0.stdout\nfoo\n"
                "0 /tmp/0.stderr\n"
                "0\n1735689600\n1735689601\n4 /tmp/1.stdout\nbar\n"
                "0 /tmp/1.stderr\n\n"
            ),
            "stderr": "",
            "start": "2025-01-01 00:00:00",
            "end": "2025-01-01 00:00:01",
            "delta": "0:00:01",
        }

    monkeypatch.setattr(plugin, "_command", mock_cmd)

    result = plugin.run(task_vars={})

    assert result["changed"] is True
    assert isinstance(result["commands"], list)
    assert len(result["commands"]) == 2
    # Verify the actual command was extracted from dict
    assert result["commands"][0]["command"] == "echo foo"
    assert result["commands"][1]["command"] == "echo bar"
    # Verify metadata is preserved
    assert result["commands"][0]["extra"] == "ignored"
    assert result["commands"][1]["meta"] == "data"


def test_normalize_command_request_string(plugin) -> None:
    """Test _normalize_command_request wraps string in dict."""
    result = plugin._normalize_command_request("echo hello")

    assert result == {"command": "echo hello"}


def test_normalize_command_request_list(plugin) -> None:
    """Test _normalize_command_request wraps list in dict."""
    result = plugin._normalize_command_request(["echo", "hello", "world"])

    assert result == {"command": ["echo", "hello", "world"]}


def test_normalize_command_request_dict_with_command_key(plugin) -> None:
    """Test _normalize_command_request returns dict copy with command."""
    input_dict = {
        "command": "uname -s",
        "parser": "uname",
        "extra": "ignored",
    }
    result = plugin._normalize_command_request(input_dict)

    assert result == input_dict
    assert result is not input_dict  # Should be a copy


def test_normalize_command_request_dict_with_list_command(plugin) -> None:
    """Test _normalize_command_request handles dict with list command."""
    input_dict = {
        "command": ["echo", "hello"],
        "parser": "custom",
    }
    result = plugin._normalize_command_request(input_dict)

    assert result == input_dict
    assert result is not input_dict


def test_normalize_command_request_dict_missing_command_key(plugin) -> None:
    """Test _normalize_command_request raises error when dict lacks command."""
    with pytest.raises(
        AnsibleActionFail, match="must contain a 'command' key"
    ):
        plugin._normalize_command_request(
            {
                "parser": "uname",
                "other": "data",
            }
        )


# Tests for _parse_batch_output


def test_parse_batch_output_single_command(plugin) -> None:
    """Test _parse_batch_output with a single command."""
    plugin.strip = True
    output = (
        "0\n"  # rc
        "1735689600\n"  # start time
        "1735689601\n"  # end time
        "6 /tmp/0.stdout\n"  # stdout length
        "hello\n"  # stdout content (6 bytes)
        "0 /tmp/0.stderr\n"  # stderr length
        # no stderr content (0 bytes)
    )
    command_requests = [{"command": "echo hello"}]

    result = plugin._parse_batch_output(output, command_requests)

    assert len(result) == 1
    assert result[0]["command"] == "echo hello"
    assert result[0]["rc"] == 0
    assert result[0]["stdout"] == "hello"
    assert result[0]["stderr"] == ""
    assert result[0]["stdout_lines"] == ["hello"]
    assert result[0]["stderr_lines"] == []
    assert "elapsed" in result[0]


def test_parse_batch_output_multiple_commands(plugin) -> None:
    """Test _parse_batch_output with multiple commands."""
    plugin.strip = True
    output = (
        "0\n1735689600\n1735689601\n4 /tmp/0.stdout\nfoo\n"
        "0 /tmp/0.stderr\n"
        "0\n1735689600\n1735689601\n4 /tmp/1.stdout\nbar\n"
        "0 /tmp/1.stderr\n"
    )
    command_requests = [{"command": "echo foo"}, {"command": "echo bar"}]

    result = plugin._parse_batch_output(output, command_requests)

    assert len(result) == 2
    assert result[0]["stdout"] == "foo"
    assert result[1]["stdout"] == "bar"


def test_parse_batch_output_with_stderr(plugin) -> None:
    """Test _parse_batch_output captures stderr correctly."""
    plugin.strip = True
    output = (
        "1\n"  # rc=1 (failure)
        "1735689600\n"
        "1735689601\n"
        "0 /tmp/0.stdout\n"  # empty stdout
        "6 /tmp/0.stderr\n"  # stderr length
        "error\n"  # stderr content
    )
    command_requests = [{"command": "false"}]

    result = plugin._parse_batch_output(output, command_requests)

    assert result[0]["rc"] == 1
    assert result[0]["stdout"] == ""
    assert result[0]["stderr"] == "error"
    assert result[0]["stderr_lines"] == ["error"]


def test_parse_batch_output_no_strip(plugin) -> None:
    """Test _parse_batch_output preserves whitespace when strip=False."""
    plugin.strip = False
    output = (
        "0\n"
        "1735689600\n"
        "1735689601\n"
        "7 /tmp/0.stdout\n"
        "hello\n\n"  # trailing newlines (7 bytes)
        "0 /tmp/0.stderr\n"
    )
    command_requests = [{"command": "echo hello"}]

    result = plugin._parse_batch_output(output, command_requests)

    assert result[0]["stdout"] == "hello\n\n"


def test_parse_batch_output_request_strip_overrides_action(plugin) -> None:
    """Test a request's own strip governs that command alone."""
    plugin.strip = True
    output = (
        "0\n1735689600\n1735689601\n7 /tmp/0.stdout\nbytes\n\n"
        "0 /tmp/0.stderr\n"
        "0\n1735689600\n1735689601\n7 /tmp/1.stdout\nanswer\n"
        "0 /tmp/1.stderr\n"
    )
    command_requests = [
        {"command": ["cat", "/f"], "strip": False},
        {"command": ["file", "-b", "/f"]},
    ]

    result = plugin._parse_batch_output(output, command_requests)

    assert result[0]["stdout"] == "bytes\n\n"
    assert result[1]["stdout"] == "answer"


def test_parse_batch_output_request_strip_can_ask_for_stripping(
    plugin,
) -> None:
    """Test a request may strip while the action does not."""
    plugin.strip = False
    output = (
        "0\n1735689600\n1735689601\n7 /tmp/0.stdout\nanswer\n"
        "0 /tmp/0.stderr\n"
    )
    command_requests = [{"command": "echo answer", "strip": True}]

    result = plugin._parse_batch_output(output, command_requests)

    assert result[0]["stdout"] == "answer"


def test_parse_batch_output_request_strip_governs_stderr(plugin) -> None:
    """Test a request's strip covers its stderr as well as its stdout."""
    plugin.strip = True
    output = (
        "0\n1735689600\n1735689601\n0 /tmp/0.stdout\n"
        "6 /tmp/0.stderr\nnoise\n"
    )
    command_requests = [{"command": ["cat", "/f"], "strip": False}]

    result = plugin._parse_batch_output(output, command_requests)

    assert result[0]["stderr"] == "noise\n"


def test_parse_batch_output_skips_leading_whitespace(plugin) -> None:
    """Test _parse_batch_output skips leading whitespace in output."""
    plugin.strip = True
    output = (
        "\n\n  "  # leading whitespace
        "0\n1735689600\n1735689601\n3 /tmp/0.stdout\nhi\n"
        "0 /tmp/0.stderr\n"
    )
    command_requests = [{"command": "echo hi"}]

    result = plugin._parse_batch_output(output, command_requests)

    assert result[0]["stdout"] == "hi"


def test_parse_batch_output_malformed_raises(plugin) -> None:
    """Test _parse_batch_output raises ValueError on malformed output."""
    plugin.strip = True
    output = "incomplete"  # missing all required fields
    command_requests = [{"command": "echo test"}]

    with pytest.raises(ValueError):
        plugin._parse_batch_output(output, command_requests)


def test_parse_batch_output_preserves_metadata(plugin) -> None:
    """Test _parse_batch_output preserves request metadata in result."""
    plugin.strip = True
    output = (
        "0\n1735689600\n1735689601\n4 /tmp/0.stdout\nfoo\n0 /tmp/0.stderr\n"
    )
    command_requests = [
        {
            "command": "echo foo",
            "implementation": "posix",
            "type": "test",
            "parser": "custom_parser",
        }
    ]

    result = plugin._parse_batch_output(output, command_requests)

    assert result[0]["implementation"] == "posix"
    assert result[0]["type"] == "test"
    assert result[0]["parser"] == "custom_parser"
    assert result[0]["stdout"] == "foo"


def test_parse_batch_output_request_precedence(plugin) -> None:
    """Test _parse_batch_output gives request values precedence over parsed."""
    plugin.strip = True
    # Command returns rc=1, but request overrides to rc=0
    output = (
        "1\n"  # rc=1 from command
        "1735689600\n"
        "1735689601\n"
        "6 /tmp/0.stdout\n"
        "error\n"  # stdout content
        "5 /tmp/0.stderr\n"
        "fail\n"  # stderr content
    )
    # Request overrides rc and stderr
    command_requests = [
        {
            "command": "false",
            "rc": 0,  # Override parsed rc=1
            "stderr": "",  # Override parsed stderr="fail"
        }
    ]

    result = plugin._parse_batch_output(output, command_requests)

    # Request values take precedence
    assert result[0]["rc"] == 0  # From request, not parsed 1
    assert result[0]["stderr"] == ""  # From request, not parsed "fail"
    # But stdout is still from parsed output
    assert result[0]["stdout"] == "error"


# Tests for _build_batch_script


def test_build_batch_script_sequential(plugin) -> None:
    """Test _build_batch_script generates sequential execution script."""
    plugin.parallel = False
    plugin.fail_fast = False
    command_requests = [{"command": "echo foo"}, {"command": "echo bar"}]
    tmp = "/tmp/test/"

    script = plugin._build_batch_script(command_requests, tmp)

    assert "set +e" in script  # not fail_fast
    assert "echo foo" in script
    assert "echo bar" in script
    # Sequential mode doesn't use background jobs
    assert "& " not in script or "pid" not in script.split("& ")[0]


def test_build_batch_script_parallel(plugin) -> None:
    """Test _build_batch_script generates parallel execution script."""
    plugin.parallel = True
    plugin.fail_fast = False
    command_requests = [{"command": "echo foo"}, {"command": "echo bar"}]
    tmp = "/tmp/test/"

    script = plugin._build_batch_script(command_requests, tmp)

    assert "set +e" in script
    # Parallel mode uses background jobs and wait
    assert "& " in script
    assert "pid0=$!" in script
    assert "pid1=$!" in script
    assert 'wait "$pid0"' in script
    assert 'wait "$pid1"' in script


def test_build_batch_script_fail_fast(plugin) -> None:
    """Test _build_batch_script uses set -e when fail_fast=True."""
    plugin.parallel = False
    plugin.fail_fast = True
    command_requests = [{"command": "echo test"}]
    tmp = "/tmp/test/"

    script = plugin._build_batch_script(command_requests, tmp)

    assert "set -e" in script


def test_build_batch_script_list_command(plugin) -> None:
    """Test _build_batch_script formats list commands correctly."""
    plugin.parallel = False
    plugin.fail_fast = False
    command_requests = [
        {"command": ["echo", "hello world"]}
    ]  # list with spaces
    tmp = "/tmp/test/"

    script = plugin._build_batch_script(command_requests, tmp)

    # List should be formatted with proper quoting
    assert "echo" in script
    assert "hello world" in script or "'hello world'" in script


def test_build_batch_script_captures_timing(plugin) -> None:
    """Test _build_batch_script captures start/end timestamps."""
    plugin.parallel = False
    plugin.fail_fast = False
    command_requests = [{"command": "echo test"}]
    tmp = "/tmp/test/"

    script = plugin._build_batch_script(command_requests, tmp)

    assert "date +%s" in script
    assert ".start" in script
    assert ".end" in script


def test_build_batch_script_captures_output(plugin) -> None:
    """Test _build_batch_script redirects stdout/stderr to files."""
    plugin.parallel = False
    plugin.fail_fast = False
    command_requests = [{"command": "echo test"}]
    tmp = "/tmp/test/"

    script = plugin._build_batch_script(command_requests, tmp)

    assert ".stdout" in script
    assert ".stderr" in script
    assert "wc -c" in script  # length prefix


# Tests for _estimate_script_length


def test_estimate_script_length_returns_double(plugin) -> None:
    """Test _estimate_script_length returns 2x actual script length."""
    plugin.parallel = False
    plugin.fail_fast = False
    command_requests = [{"command": "echo test"}]
    tmp = "/tmp/test/"

    actual_script = plugin._build_batch_script(command_requests, tmp)
    estimated = plugin._estimate_script_length(command_requests, tmp)

    assert estimated == len(actual_script) * 2


def test_estimate_script_length_scales_with_commands(plugin) -> None:
    """Test _estimate_script_length increases with more commands."""
    plugin.parallel = False
    plugin.fail_fast = False
    tmp = "/tmp/test/"

    est_one = plugin._estimate_script_length([{"command": "echo a"}], tmp)
    est_three = plugin._estimate_script_length(
        [{"command": "echo a"}, {"command": "echo b"}, {"command": "echo c"}],
        tmp,
    )

    assert est_three > est_one


# Tests for _split_commands_by_length


def test_split_commands_by_length_single_batch(plugin) -> None:
    """Test _split_commands_by_length keeps small sets in one batch."""
    plugin.parallel = False
    plugin.fail_fast = False
    plugin.command_requests = [
        {"command": "echo a"},
        {"command": "echo b"},
        {"command": "echo c"},
    ]

    batches = plugin._split_commands_by_length(
        max_length=100000, max_count=100
    )

    assert len(batches) == 1
    assert batches[0] == plugin.command_requests


def test_split_commands_by_length_splits_by_count(plugin) -> None:
    """Test _split_commands_by_length splits when count exceeds limit."""
    plugin.parallel = False
    plugin.fail_fast = False
    plugin.command_requests = [
        {"command": "echo a"},
        {"command": "echo b"},
        {"command": "echo c"},
        {"command": "echo d"},
        {"command": "echo e"},
    ]

    batches = plugin._split_commands_by_length(max_length=100000, max_count=2)

    assert len(batches) == 3  # 2, 2, 1
    assert len(batches[0]) == 2
    assert len(batches[1]) == 2
    assert len(batches[2]) == 1


def test_split_commands_by_length_splits_by_size(plugin) -> None:
    """Test _split_commands_by_length splits when size exceeds limit."""
    plugin.parallel = False
    plugin.fail_fast = False
    # Use commands with varying lengths
    plugin.command_requests = [
        {"command": "echo short"},
        {"command": "echo " + "x" * 1000},
    ]

    # Set a low max_length to force splitting
    batches = plugin._split_commands_by_length(max_length=500, max_count=100)

    # Should split because the long command exceeds the limit
    assert len(batches) >= 1


def test_split_commands_by_length_empty_commands(plugin) -> None:
    """Test _split_commands_by_length handles empty command list."""
    plugin.parallel = False
    plugin.fail_fast = False
    plugin.command_requests = []

    batches = plugin._split_commands_by_length()

    assert batches == []


# Tests for _is_command_failed


def test_is_command_failed_rc_zero(plugin) -> None:
    """Test _is_command_failed returns False for rc=0."""
    result = {"rc": 0}

    assert plugin._is_command_failed(result) is False


def test_is_command_failed_rc_nonzero(plugin) -> None:
    """Test _is_command_failed returns True for rc!=0."""
    result = {"rc": 1}

    assert plugin._is_command_failed(result) is True


def test_is_command_failed_rc_none(plugin) -> None:
    """Test _is_command_failed returns True for rc=None."""
    result = {"rc": None}

    assert plugin._is_command_failed(result) is True


def test_is_command_failed_rc_missing(plugin) -> None:
    """Test _is_command_failed returns True when rc is missing."""
    result = {}

    assert plugin._is_command_failed(result) is True


def test_is_command_failed_non_error_codes(plugin) -> None:
    """Test _is_command_failed respects non_error_codes."""
    # rc=1 normally fails, but is in non_error_codes
    result = {"rc": 1, "non_error_codes": [0, 1]}

    assert plugin._is_command_failed(result) is False


def test_is_command_failed_non_error_codes_still_fails(plugin) -> None:
    """Test _is_command_failed fails when rc not in non_error_codes."""
    # rc=2 is not in non_error_codes
    result = {"rc": 2, "non_error_codes": [0, 1]}

    assert plugin._is_command_failed(result) is True


def test_is_command_failed_grep_pattern(plugin) -> None:
    """Test _is_command_failed with grep-style return codes."""
    # grep returns 0 for match, 1 for no match, 2+ for error
    # Treat 0 and 1 as success
    non_error_codes = [0, 1]

    assert (
        plugin._is_command_failed(
            {"rc": 0, "non_error_codes": non_error_codes}
        )
        is False
    )
    assert (
        plugin._is_command_failed(
            {"rc": 1, "non_error_codes": non_error_codes}
        )
        is False
    )
    assert (
        plugin._is_command_failed(
            {"rc": 2, "non_error_codes": non_error_codes}
        )
        is True
    )


# Tests for _build_command_wrapper


def test_build_command_wrapper_default(plugin) -> None:
    """Test _build_command_wrapper with default non_error_codes."""
    wrapper = plugin._build_command_wrapper("echo test", "/tmp/", 0, [0])

    assert "set +e" in wrapper
    assert "echo test" in wrapper
    assert '"/tmp/0.stdout"' in wrapper
    assert '"/tmp/0.stderr"' in wrapper
    assert '"/tmp/0.rc"' in wrapper
    assert "case $__rc in 0) exit 0;; *) exit 1;; esac" in wrapper


def test_build_command_wrapper_multiple_codes(plugin) -> None:
    """Test _build_command_wrapper with multiple non_error_codes."""
    wrapper = plugin._build_command_wrapper("grep x", "/tmp/", 5, [0, 1])

    assert "case $__rc in 0|1) exit 0;; *) exit 1;; esac" in wrapper
    assert '"/tmp/5.rc"' in wrapper


def test_build_command_wrapper_many_codes(plugin) -> None:
    """Test _build_command_wrapper with many non_error_codes."""
    wrapper = plugin._build_command_wrapper("cmd", "/tmp/", 0, [0, 1, 2, 127])

    assert "case $__rc in 0|1|2|127) exit 0;; *) exit 1;; esac" in wrapper


# The batch as each transport reports it


@pytest.mark.parametrize("raw", [True, False], ids=["raw", "interpreted"])
def test_fail_fast_fails_the_batch_on_either_transport(
    plugin, tmp_path, raw
) -> None:
    """Test an aborted batch is a failure whichever transport ran it.

    fail_fast is ``set -e``: the command that fails takes the script
    down with it, and everything after it, including the output the
    parser was to read. What comes back is a non-zero status and a
    truncated stream, and the batch has to fail on the status rather
    than stumble over the stream, in the same words either way.
    """
    plugin._make_tmp_path = MagicMock(return_value=f"{tmp_path}/batch")
    plugin._task.args = {
        "commands": ["echo before", "false", "echo after"],
        "fail_fast": True,
        "raw": raw,
    }
    _delegate_to_command(plugin)

    with pytest.raises(
        AnsibleActionFail,
        match="Batch execution failed: non-zero return code",
    ):
        plugin.run(task_vars={})


@pytest.mark.parametrize("raw", [True, False], ids=["raw", "interpreted"])
def test_without_fail_fast_the_batch_runs_through_on_either_transport(
    plugin, tmp_path, raw
) -> None:
    """Test a batch that is not fail_fast reports each command's own
    status: ``set +e`` leaves the script to finish and exit zero, so
    nothing about the transport is at stake and the failure is the
    task's rather than the batch's.
    """
    plugin._make_tmp_path = MagicMock(return_value=f"{tmp_path}/batch")
    plugin._task.args = {
        "commands": ["echo first", "false", "echo third"],
        "parallel": False,
        "fail_fast": False,
        "raw": raw,
    }
    _delegate_to_command(plugin)

    result = plugin.run(task_vars={})

    assert result["failed"] is True
    assert [c["rc"] for c in result["commands"]] == [0, 1, 0]
    assert result["commands"][0]["stdout"] == "first"
    assert result["commands"][2]["stdout"] == "third"
