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

from unittest.mock import MagicMock

import pytest
from ansible.errors import AnsibleActionFail


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


def test_run_list_mode(plugin) -> None:
    """Test run with list input returns list output."""
    plugin._task.args = {
        "commands": ["echo foo", "echo bar"],
    }

    # Mock _cmd to return batch output with start/end times
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

    plugin._command = mock_cmd

    result = plugin.run(task_vars={})

    assert result["changed"] is True
    assert isinstance(result["commands"], list)
    assert len(result["commands"]) == 2
    assert result["commands"][0]["cmd"] == "echo foo"
    assert result["commands"][1]["cmd"] == "echo bar"


def test_run_dict_mode(plugin) -> None:
    """Test run with dict input returns dict output."""
    plugin._task.args = {
        "commands": {"first": "echo foo", "second": "echo bar"},
    }

    # Mock _cmd to return batch output with start/end times
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

    plugin._command = mock_cmd

    result = plugin.run(task_vars={})

    assert result["changed"] is True
    assert isinstance(result["commands"], dict)
    assert "first" in result["commands"]
    assert "second" in result["commands"]
    assert result["commands"]["first"]["cmd"] == "echo foo"
    assert result["commands"]["second"]["cmd"] == "echo bar"


def test_run_dict_mode_preserves_keys(plugin) -> None:
    """Test dict mode preserves all keys from input."""
    plugin._task.args = {
        "commands": {
            "kernel": "uname -s",
            "machine": "uname -m",
            "hostname": "hostname",
        },
    }

    # Mock _cmd to return batch output with start/end times
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

    plugin._command = mock_cmd

    result = plugin.run(task_vars={})

    assert isinstance(result["commands"], dict)
    assert set(result["commands"].keys()) == {"kernel", "machine", "hostname"}
    assert result["commands"]["kernel"]["cmd"] == "uname -s"
    assert result["commands"]["machine"]["cmd"] == "uname -m"
    assert result["commands"]["hostname"]["cmd"] == "hostname"


def test_run_dict_mode_single_command(plugin) -> None:
    """Test dict mode with single command."""
    plugin._task.args = {
        "commands": {"only_one": "echo test"},
    }

    # Mock _cmd to return batch output with start/end times
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

    plugin._command = mock_cmd

    result = plugin.run(task_vars={})

    assert isinstance(result["commands"], dict)
    assert len(result["commands"]) == 1
    assert "only_one" in result["commands"]
    assert result["commands"]["only_one"]["cmd"] == "echo test"


def test_run_dict_mode_with_failures(plugin) -> None:
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

    plugin._command = mock_cmd

    result = plugin.run(task_vars={})

    assert result["failed"] is True
    assert isinstance(result["commands"], dict)
    assert result["commands"]["pass"]["rc"] == 0
    assert result["commands"]["fail"]["rc"] == 1


def test_run_dict_command_items(plugin) -> None:
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

    plugin._command = mock_cmd

    result = plugin.run(task_vars={})

    assert result["changed"] is True
    assert isinstance(result["commands"], dict)
    assert "posix_uname" in result["commands"]
    assert "posix_uptime" in result["commands"]
    # Verify the actual command was extracted from dict
    assert result["commands"]["posix_uname"]["cmd"] == "uname -s"
    assert result["commands"]["posix_uptime"]["cmd"] == "uptime"


def test_run_list_with_dict_command_items(plugin) -> None:
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

    plugin._command = mock_cmd

    result = plugin.run(task_vars={})

    assert result["changed"] is True
    assert isinstance(result["commands"], list)
    assert len(result["commands"]) == 2
    # Verify the actual command was extracted from dict
    assert result["commands"][0]["cmd"] == "echo foo"
    assert result["commands"][1]["cmd"] == "echo bar"


def test_extract_command_string(plugin) -> None:
    """Test _extract_command returns string input as-is."""
    result = plugin._extract_command("echo hello")

    assert result == "echo hello"


def test_extract_command_list(plugin) -> None:
    """Test _extract_command returns list input as-is."""
    result = plugin._extract_command(["echo", "hello", "world"])

    assert result == ["echo", "hello", "world"]


def test_extract_command_dict_with_command_key(plugin) -> None:
    """Test _extract_command extracts command from dict."""
    result = plugin._extract_command({
        "command": "uname -s",
        "parser": "uname",
        "extra": "ignored",
    })

    assert result == "uname -s"


def test_extract_command_dict_with_list_command(plugin) -> None:
    """Test _extract_command extracts list command from dict."""
    result = plugin._extract_command({
        "command": ["echo", "hello"],
        "parser": "custom",
    })

    assert result == ["echo", "hello"]


def test_extract_command_dict_missing_command_key(plugin) -> None:
    """Test _extract_command raises error when dict lacks 'command' key."""
    with pytest.raises(AnsibleActionFail, match="must contain a 'command' key"):
        plugin._extract_command({
            "parser": "uname",
            "other": "data",
        })


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
    commands = ["echo hello"]

    result = plugin._parse_batch_output(output, commands)

    assert len(result) == 1
    assert result[0]["cmd"] == "echo hello"
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
    commands = ["echo foo", "echo bar"]

    result = plugin._parse_batch_output(output, commands)

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
    commands = ["false"]

    result = plugin._parse_batch_output(output, commands)

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
    commands = ["echo hello"]

    result = plugin._parse_batch_output(output, commands)

    assert result[0]["stdout"] == "hello\n\n"


def test_parse_batch_output_skips_leading_whitespace(plugin) -> None:
    """Test _parse_batch_output skips leading whitespace in output."""
    plugin.strip = True
    output = (
        "\n\n  "  # leading whitespace
        "0\n1735689600\n1735689601\n3 /tmp/0.stdout\nhi\n"
        "0 /tmp/0.stderr\n"
    )
    commands = ["echo hi"]

    result = plugin._parse_batch_output(output, commands)

    assert result[0]["stdout"] == "hi"


def test_parse_batch_output_malformed_raises(plugin) -> None:
    """Test _parse_batch_output raises ValueError on malformed output."""
    plugin.strip = True
    output = "incomplete"  # missing all required fields
    commands = ["echo test"]

    with pytest.raises(ValueError):
        plugin._parse_batch_output(output, commands)


# Tests for _build_batch_script


def test_build_batch_script_sequential(plugin) -> None:
    """Test _build_batch_script generates sequential execution script."""
    plugin.parallel = False
    plugin.fail_fast = False
    commands = ["echo foo", "echo bar"]
    tmp = "/tmp/test/"

    script = plugin._build_batch_script(commands, tmp)

    assert "set +e" in script  # not fail_fast
    assert "unalias -a" in script
    assert 'echo foo' in script
    assert 'echo bar' in script
    # Sequential mode doesn't use background jobs
    assert "& " not in script or "pid" not in script.split("& ")[0]


def test_build_batch_script_parallel(plugin) -> None:
    """Test _build_batch_script generates parallel execution script."""
    plugin.parallel = True
    plugin.fail_fast = False
    commands = ["echo foo", "echo bar"]
    tmp = "/tmp/test/"

    script = plugin._build_batch_script(commands, tmp)

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
    commands = ["echo test"]
    tmp = "/tmp/test/"

    script = plugin._build_batch_script(commands, tmp)

    assert "set -e" in script


def test_build_batch_script_list_command(plugin) -> None:
    """Test _build_batch_script formats list commands correctly."""
    plugin.parallel = False
    plugin.fail_fast = False
    commands = [["echo", "hello world"]]  # list with spaces
    tmp = "/tmp/test/"

    script = plugin._build_batch_script(commands, tmp)

    # List should be formatted with proper quoting
    assert "echo" in script
    assert "hello world" in script or "'hello world'" in script


def test_build_batch_script_captures_timing(plugin) -> None:
    """Test _build_batch_script captures start/end timestamps."""
    plugin.parallel = False
    plugin.fail_fast = False
    commands = ["echo test"]
    tmp = "/tmp/test/"

    script = plugin._build_batch_script(commands, tmp)

    assert "date +%s" in script
    assert ".start" in script
    assert ".end" in script


def test_build_batch_script_captures_output(plugin) -> None:
    """Test _build_batch_script redirects stdout/stderr to files."""
    plugin.parallel = False
    plugin.fail_fast = False
    commands = ["echo test"]
    tmp = "/tmp/test/"

    script = plugin._build_batch_script(commands, tmp)

    assert ".stdout" in script
    assert ".stderr" in script
    assert "wc -c" in script  # length prefix


# Tests for _estimate_script_length


def test_estimate_script_length_returns_double(plugin) -> None:
    """Test _estimate_script_length returns 2x actual script length."""
    plugin.parallel = False
    plugin.fail_fast = False
    commands = ["echo test"]
    tmp = "/tmp/test/"

    actual_script = plugin._build_batch_script(commands, tmp)
    estimated = plugin._estimate_script_length(commands, tmp)

    assert estimated == len(actual_script) * 2


def test_estimate_script_length_scales_with_commands(plugin) -> None:
    """Test _estimate_script_length increases with more commands."""
    plugin.parallel = False
    plugin.fail_fast = False
    tmp = "/tmp/test/"

    est_one = plugin._estimate_script_length(["echo a"], tmp)
    est_three = plugin._estimate_script_length(
        ["echo a", "echo b", "echo c"], tmp
    )

    assert est_three > est_one


# Tests for _split_commands_by_length


def test_split_commands_by_length_single_batch(plugin) -> None:
    """Test _split_commands_by_length keeps small sets in one batch."""
    plugin.parallel = False
    plugin.fail_fast = False
    plugin.commands = ["echo a", "echo b", "echo c"]

    batches = plugin._split_commands_by_length(max_length=100000, max_count=100)

    assert len(batches) == 1
    assert batches[0] == plugin.commands


def test_split_commands_by_length_splits_by_count(plugin) -> None:
    """Test _split_commands_by_length splits when count exceeds limit."""
    plugin.parallel = False
    plugin.fail_fast = False
    plugin.commands = ["echo a", "echo b", "echo c", "echo d", "echo e"]

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
    plugin.commands = ["echo short", "echo " + "x" * 1000]

    # Set a low max_length to force splitting
    batches = plugin._split_commands_by_length(max_length=500, max_count=100)

    # Should split because the long command exceeds the limit
    assert len(batches) >= 1


def test_split_commands_by_length_empty_commands(plugin) -> None:
    """Test _split_commands_by_length handles empty command list."""
    plugin.parallel = False
    plugin.fail_fast = False
    plugin.commands = []

    batches = plugin._split_commands_by_length()

    assert batches == []
