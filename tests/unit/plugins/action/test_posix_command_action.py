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

"""Unit tests for the command action plugin.

The action owns two transports and the seam between them, and until
now only the integration target pinned either. These tests stub the
two transports and nothing else: argument validation, the quoting,
the creates and removes probes, the chdir check and the output
normalization are the plugin's own, and the raw transport runs what
it is handed through a real shell.

The transport answers with the three fields a POSIX transport
answers with and no line forms. ansible-core 2.21 returns those
forms from ``_low_level_execute_command`` itself, which is what hid
the defect at 9a27555 from every test that ran on it; a stub that
supplied them would hide it again, so the answers here are the
pre-2.21 shape and the action has to publish the forms itself.
"""

from __future__ import annotations

import shlex
import subprocess
from typing import Any, Generator, Optional

import pytest

from ansible.errors import AnsibleActionFail
from ansible_collections.o0_o.posix.plugins.action import command
from ansible_collections.o0_o.posix.plugins.action.command import (
    ActionModule,
)

# What ansible-core says when the module could not find a python
INTERPRETER_MISSING = {
    "rc": 127,
    "failed": True,
    "msg": (
        "The module failed to execute correctly, you probably need to "
        "set the interpreter for this host"
    ),
    "module_stderr": "/usr/bin/python3: not found",
}

# What the builtin command module answers with when it ran
NATIVE_OK = {
    "rc": 0,
    "changed": True,
    "stdout": "",
    "stderr": "",
    "stdout_lines": [],
    "stderr_lines": [],
    "invocation": {"module_args": {"_raw_params": "true"}},
}

# The transport calls that are the action asking about the host
# rather than the action running the command it was given
PROBES = ("cd ", "test -e ")

# A variable nothing but these tests sets, so what a transport
# expanded and what it left alone is unambiguous
VARIABLE = "O0_O_COMMAND_TEST"


def _run_locally(cmd: str, in_data: Optional[bytes] = None) -> dict[str, Any]:
    """Run what the action handed the transport, for real.

    A POSIX transport hands the command string to a shell on the
    target and reports what it said, so running it here through the
    local shell exercises the quoting the action built rather than a
    test's opinion of it.

    :param str cmd: The command string the action sent
    :param Optional[bytes] in_data: Standard input for the command
    :returns dict[str, Any]: The transport's answer
    """
    completed = subprocess.run(
        cmd,
        shell=True,
        input=in_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "rc": completed.returncode,
        "stdout": completed.stdout.decode("utf-8"),
        "stderr": completed.stderr.decode("utf-8"),
    }


def _says(rc: int = 0, stdout: str = "", stderr: str = "") -> Any:
    """Answer every transport call with one canned result.

    :param int rc: The return code to report
    :param str stdout: The standard output to report
    :param str stderr: The standard error to report
    :returns Any: A transport answer function
    """

    def answer(cmd: str, in_data: Optional[bytes] = None) -> dict[str, Any]:
        return {"rc": rc, "stdout": stdout, "stderr": stderr}

    return answer


class _StubbedTransports(ActionModule):
    """The command action with both of its transports recorded.

    The seams are overridden on a subclass rather than assigned to
    the instance, so an override has to keep matching the call the
    action makes; if the action ever stops calling one of them, the
    inherited method runs against the mocked plumbing and the call
    log stays empty rather than the test passing quietly.
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
        """Record the raw transport call and answer it."""
        self.transport_calls.append(
            {
                "cmd": cmd,
                "sudoable": sudoable,
                "in_data": in_data,
                "executable": executable,
                "chdir": chdir,
            }
        )
        return self.transport_answer(cmd, in_data)

    def _execute_module(
        self,
        module_name: Optional[str] = None,
        module_args: Optional[dict[str, Any]] = None,
        task_vars: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Record the native delegation and answer it."""
        self.module_calls.append(
            {"module_name": module_name, "module_args": module_args}
        )
        return dict(self.module_answer)


@pytest.fixture
def plugin(base) -> Generator[ActionModule, None, None]:
    """Build the command action over recorded transports.

    :param base: The mocked action plumbing from the package conftest
    :returns: The action instance, its temporary directory intact
    """
    base._task.async_val = False
    base._task.action = "o0_o.posix.command"
    base._task.check_mode = False
    base._task.args = {}
    base._play_context.become = False

    plugin = _StubbedTransports(
        task=base._task,
        connection=base._connection,
        play_context=base._play_context,
        loader=base._loader,
        templar=base._templar,
        shared_loader_obj=base._shared_loader_obj,
    )
    plugin._display = base._display
    plugin.inventory_hostname = "localhost"
    plugin.transport_calls = []
    plugin.module_calls = []
    plugin.transport_answer = _run_locally
    plugin.module_answer = NATIVE_OK
    yield plugin


def _run(
    plugin: ActionModule,
    args: dict[str, Any],
    check_mode: bool = False,
) -> dict[str, Any]:
    """Run the action with the given task arguments.

    :param ActionModule plugin: The action instance
    :param dict[str, Any] args: The task's arguments
    :param bool check_mode: Whether the task runs in check mode
    :returns dict[str, Any]: The action's own result dict
    """
    plugin._task.args = dict(args)
    plugin._task.check_mode = check_mode
    return plugin.run(task_vars={})


def _execution(plugin: ActionModule) -> Optional[dict[str, Any]]:
    """Return the transport call that carried the command itself.

    The chdir check and the creates and removes probes ride the same
    transport, so the execution is the call that is none of them.

    :param ActionModule plugin: The action instance
    :returns Optional[dict[str, Any]]: The call, or None if the
        command never ran
    """
    calls = [
        call
        for call in plugin.transport_calls
        if not call["cmd"].startswith(PROBES)
    ]
    assert len(calls) <= 1, f"more than one execution: {calls}"
    return calls[0] if calls else None


def _payload(sent: str) -> str:
    """Return what the one shell layer was asked to run.

    :param str sent: The command string the action sent
    :returns str: The payload the shell layer carries
    """
    argv = shlex.split(sent)
    assert argv[:2] == ["/bin/sh", "-c"], f"not a shell layer: {sent}"
    assert len(argv) == 3, f"more than a shell layer: {sent}"
    return argv[2]


# The raw and native split


def test_raw_true_never_asks_the_interpreter(plugin) -> None:
    """Test raw=true runs on the raw transport without delegating.

    A host chosen for raw execution has no interpreter to spend a
    round trip failing against.
    """
    result = _run(plugin, {"cmd": "echo hi", "raw": True})

    assert plugin.module_calls == []
    assert _execution(plugin) is not None
    assert result["raw"] is True
    assert result["stdout"] == "hi"


def test_raw_false_delegates_to_the_builtin_module(plugin) -> None:
    """Test raw=false runs the builtin module and nothing else."""
    result = _run(plugin, {"cmd": "echo hi", "raw": False})

    assert [call["module_name"] for call in plugin.module_calls] == [
        "ansible.builtin.command"
    ]
    assert _execution(plugin) is None
    assert result["raw"] is False


def test_auto_stays_native_when_the_module_answers(plugin) -> None:
    """Test auto is native when the interpreter is there, since the
    raw fallback is a fallback rather than a preference."""
    result = _run(plugin, {"cmd": "echo hi"})

    assert len(plugin.module_calls) == 1
    assert _execution(plugin) is None
    assert result["raw"] is False


def test_auto_descends_to_raw_when_the_interpreter_is_missing(
    plugin,
) -> None:
    """Test auto falls back to raw, and says so, when the module
    could not find a python on the host."""
    plugin.module_answer = INTERPRETER_MISSING

    result = _run(plugin, {"cmd": "echo hi", "raw": "auto"})

    assert len(plugin.module_calls) == 1
    assert _execution(plugin) is not None
    assert result["raw"] is True
    assert result["rc"] == 0
    assert result["stdout"] == "hi"
    plugin._display.warning.assert_called()


def test_raw_false_returns_the_interpreter_failure(plugin) -> None:
    """Test raw=false is a refusal to fall back: a host without an
    interpreter fails as the module failed, rather than descending."""
    plugin.module_answer = INTERPRETER_MISSING

    result = _run(plugin, {"cmd": "echo hi", "raw": False})

    assert _execution(plugin) is None
    assert result["rc"] == 127
    assert result["failed"] is True
    assert result["raw"] is False


def test_a_command_that_exits_127_is_not_a_missing_interpreter(
    plugin,
) -> None:
    """Test a command that is itself missing keeps its own failure.

    127 is what a shell says about a command it could not find, so
    the status alone cannot mean the interpreter: only the text the
    failure carries can, and this one names the command.
    """
    plugin.module_answer = {
        "rc": 127,
        "failed": True,
        "msg": "non-zero return code",
        "stderr": "/bin/sh: frobnicate: not found",
    }

    result = _run(plugin, {"cmd": "frobnicate", "raw": "auto"})

    assert _execution(plugin) is None
    assert result["raw"] is False
    assert result["rc"] == 127


def test_a_failure_that_is_not_127_never_descends(plugin) -> None:
    """Test the descent is gated on the status as well as the text.

    The check reads the return code first, so a failure that names a
    missing python without exiting 127 is the module's answer to
    keep. The action has no interpreter probe of its own to settle
    the ambiguity with.
    """
    plugin.module_answer = {
        "rc": 1,
        "failed": True,
        "msg": "python3: not found",
        "stderr": "/usr/bin/python3: not found",
    }

    result = _run(plugin, {"cmd": "echo hi", "raw": "auto"})

    assert _execution(plugin) is None
    assert result["raw"] is False
    assert result["rc"] == 1


def test_an_unknown_raw_value_is_refused(plugin) -> None:
    """Test raw takes a boolean or auto and nothing else."""
    with pytest.raises(AnsibleActionFail):
        _run(plugin, {"cmd": "echo hi", "raw": "maybe"})


# What the native delegation is asked to do


def test_native_delegation_pins_python_expansion_off(plugin) -> None:
    """Test the builtin is told not to expand arguments in python.

    Expansion belongs to the shell alone: the raw fallback has no
    interpreter to reproduce python's semantics with, so the option
    is pinned off and both transports answer alike.
    """
    _run(plugin, {"cmd": "echo $HOME", "raw": False})

    module_args = plugin.module_calls[0]["module_args"]

    assert module_args["expand_argument_vars"] is False


def test_native_delegation_omits_expansion_before_core_216(
    monkeypatch, plugin
) -> None:
    """Test a controller too old for the option is not sent it.

    expand_argument_vars arrived in ansible-core 2.16; sending it to
    an older controller is a hard argument error, and the divergence
    it leaves is documented rather than fatal.
    """
    monkeypatch.setattr(command, "ansible_version", "2.15.12")

    _run(plugin, {"cmd": "echo hi", "raw": False})

    assert "expand_argument_vars" not in plugin.module_calls[0]["module_args"]


def test_native_delegation_sends_no_null_arguments(plugin) -> None:
    """Test unset options are omitted rather than sent as null.

    The builtin refuses cmd and argv together, and a null argv is
    still argv as far as its mutual exclusion is concerned.
    """
    _run(plugin, {"cmd": "echo hi", "raw": False})

    module_args = plugin.module_calls[0]["module_args"]

    assert None not in module_args.values()
    assert "argv" not in module_args
    assert "raw" not in module_args
    assert module_args["_raw_params"] == "echo hi"


def test_the_result_names_the_command_that_was_asked_for(plugin) -> None:
    """Test the reported command is the task's, not the wrapper the
    raw transport rides in, and not the builtin's invocation."""
    result = _run(plugin, {"cmd": "echo hi", "raw": True})

    assert result["cmd"] == "echo hi"
    assert result["invocation"] == {"cmd": "echo hi", "raw": True}


def test_the_native_invocation_does_not_replace_the_action_s(
    plugin,
) -> None:
    """Test the builtin's invocation is dropped, so the result reports
    the arguments the task gave rather than the ones the delegation
    made up from them."""
    result = _run(plugin, {"cmd": "echo hi", "raw": False})

    assert result["invocation"] == {"cmd": "echo hi", "raw": False}


# One shell layer, and only one


def test_raw_execution_rides_one_shell_layer(plugin) -> None:
    """Test the raw transport is handed exactly one /bin/sh -c layer.

    Every command rides the same single layer, so what expands and
    what stays literal is the action's decision rather than the
    connection plugin's quoting.
    """
    _run(plugin, {"cmd": "echo hi", "raw": True})

    sent = _execution(plugin)["cmd"]

    assert _payload(sent) == "echo hi"


def test_a_shell_command_expands_on_the_target(monkeypatch, plugin) -> None:
    """Test _uses_shell sends the command through as written, so the
    target's shell is the one that expands it."""
    monkeypatch.setenv(VARIABLE, "expanded")

    result = _run(
        plugin,
        {"cmd": f"echo ${VARIABLE}", "_uses_shell": True, "raw": True},
    )

    assert _payload(_execution(plugin)["cmd"]) == f"echo ${VARIABLE}"
    assert result["stdout"] == "expanded"


def test_an_argv_command_stays_literal(monkeypatch, plugin) -> None:
    """Test an argument list is quoted into the same one layer, where
    nothing downstream can expand it."""
    monkeypatch.setenv(VARIABLE, "expanded")

    result = _run(plugin, {"argv": ["echo", f"${VARIABLE}"], "raw": True})

    assert result["stdout"] == f"${VARIABLE}"


def test_a_command_without_a_shell_stays_literal(monkeypatch, plugin) -> None:
    """Test a command string with no _uses_shell is quoted like an
    argument list rather than expanded, which is the divergence from
    the builtin the collection documents."""
    monkeypatch.setenv(VARIABLE, "expanded")

    result = _run(plugin, {"cmd": f"echo ${VARIABLE}", "raw": True})

    assert result["stdout"] == f"${VARIABLE}"


# Check mode predicts, and predicts without running anything


def test_check_mode_without_creates_or_removes_skips(plugin) -> None:
    """Test a bare command in check mode reports itself skipped.

    With no creates and no removes there is nothing to predict a
    change from, so the action says so instead of claiming one.
    """
    result = _run(plugin, {"cmd": "echo hi", "raw": True}, check_mode=True)

    assert result["skipped"] is True
    assert result["changed"] is False
    assert result["rc"] == 0
    assert _execution(plugin) is None


def test_check_mode_with_creates_predicts_a_change(plugin, tmp_path) -> None:
    """Test a creates that is absent predicts the change the command
    would make, without making it."""
    result = _run(
        plugin,
        {
            "cmd": "echo hi",
            "creates": str(tmp_path / "absent"),
            "raw": True,
        },
        check_mode=True,
    )

    assert result["changed"] is True
    assert "skipped" not in result
    assert _execution(plugin) is None


def test_check_mode_with_removes_predicts_a_change(plugin, tmp_path) -> None:
    """Test a removes that is present predicts the change too."""
    present = tmp_path / "present"
    present.write_text("")

    result = _run(
        plugin,
        {"cmd": "echo hi", "removes": str(present), "raw": True},
        check_mode=True,
    )

    assert result["changed"] is True
    assert "skipped" not in result
    assert _execution(plugin) is None


def test_check_mode_reports_what_it_would_not_do(plugin, tmp_path) -> None:
    """Test an existing creates in check mode reports the run it
    would not make, in the tense of a prediction."""
    present = tmp_path / "present"
    present.write_text("")

    result = _run(
        plugin,
        {"cmd": "echo hi", "creates": str(present), "raw": True},
        check_mode=True,
    )

    assert result["msg"] == f"Would not run command since '{present}' exists"
    assert result["stdout"] == f"skipped, since {present} exists"
    assert result["changed"] is False
    assert result["rc"] == 0
    assert _execution(plugin) is None


def test_an_existing_creates_reports_what_it_did_not_do(
    plugin, tmp_path
) -> None:
    """Test the same skip outside check mode is reported in the past
    tense, because it is a run that did not happen rather than one
    that would not."""
    present = tmp_path / "present"
    present.write_text("")

    result = _run(
        plugin, {"cmd": "echo hi", "creates": str(present), "raw": True}
    )

    assert result["msg"] == f"Did not run command since '{present}' exists"
    assert result["changed"] is False
    assert _execution(plugin) is None


def test_the_check_mode_message_does_not_reach_the_caller(plugin) -> None:
    """Test the check mode branch's message is lost, which is what
    the action does today rather than what it means to do.

    The branch sets 'Command would have run if not in check mode' and
    the tail then rewrites msg from the return code alone, so the
    only prediction that keeps its message is one that returns early:
    a creates that exists or a removes that does not. This pins the
    loss so that closing it is a visible change rather than a silent
    one.
    """
    result = _run(plugin, {"cmd": "echo hi", "raw": True}, check_mode=True)

    assert result["msg"] == ""


def test_an_absent_removes_skips_the_command(plugin, tmp_path) -> None:
    """Test a removes naming a path that is not there skips the run,
    since what it was to act on is already gone."""
    absent = tmp_path / "absent"

    result = _run(
        plugin, {"cmd": "echo hi", "removes": str(absent), "raw": True}
    )

    assert result["msg"] == (
        f"Did not run command since '{absent}' does not exist"
    )
    assert result["stdout"] == f"skipped, since {absent} does not exist"
    assert result["changed"] is False
    assert _execution(plugin) is None


# Empty output is still output


def test_silent_raw_output_still_publishes_its_line_forms(plugin) -> None:
    """Test a command with nothing to say publishes empty line forms.

    The forms were gated on truthy stream content, so a silent
    command omitted them entirely; ansible-core 2.21 injects the keys
    and hid that from every test that ran on it, which is why the
    transport here answers without them.
    """
    result = _run(plugin, {"cmd": "true", "raw": True})

    assert result["stdout"] == ""
    assert result["stderr"] == ""
    assert result["stdout_lines"] == []
    assert result["stderr_lines"] == []
    assert result["module_stdout"] == ""
    assert result["module_stderr"] == ""


def test_a_check_mode_prediction_publishes_its_line_forms(plugin) -> None:
    """Test a check mode prediction carries the forms as well, which
    is the case the distro matrix caught: nothing ran, so nothing set
    them, and 44 rows failed on hosts whose core did not inject."""
    result = _run(plugin, {"cmd": "true", "raw": True}, check_mode=True)

    assert result["stdout_lines"] == []
    assert result["stderr_lines"] == []
    assert result["module_stdout"] == ""
    assert result["module_stderr"] == ""


def test_a_stream_that_said_nothing_is_still_named(plugin) -> None:
    """Test a command that speaks on one stream names the other empty.

    9a27555 moved the line forms out from behind the truthy gate and
    left the module forms inside it, so a command with a quiet stream
    left that stream's module key unset where the native module names
    it "".
    """
    plugin.transport_answer = _says(stdout="said\n", stderr="")

    result = _run(plugin, {"cmd": "echo said", "raw": True})

    assert result["module_stdout"] == "said"
    assert result["module_stderr"] == ""
    assert result["stderr"] == ""
    assert result["stderr_lines"] == []


def test_a_creates_skip_publishes_its_line_forms(plugin, tmp_path) -> None:
    """Test the skip's message is its output, in both forms."""
    present = tmp_path / "present"
    present.write_text("")

    result = _run(
        plugin, {"cmd": "true", "creates": str(present), "raw": True}
    )

    assert result["stdout_lines"] == [result["stdout"]]
    assert result["stderr_lines"] == []


def test_the_native_line_forms_are_the_module_s_own(plugin) -> None:
    """Test the delegated result's line forms reach the caller.

    On this transport the forms are the builtin module's to publish
    and the action passes them through; the floor the raw path sets
    for itself is not one the action can set here.
    """
    plugin.module_answer = dict(
        NATIVE_OK, stdout="", stderr="", stdout_lines=[], stderr_lines=[]
    )

    result = _run(plugin, {"cmd": "true", "raw": False})

    assert result["stdout_lines"] == []
    assert result["stderr_lines"] == []


def test_raw_output_lines_are_the_output_split(plugin) -> None:
    """Test the line forms are the streams themselves, split."""
    plugin.transport_answer = _says(stdout="one\ntwo\n", stderr="bad\n")

    result = _run(plugin, {"cmd": "echo hi", "raw": True})

    assert result["stdout"] == "one\ntwo"
    assert result["stdout_lines"] == ["one", "two"]
    assert result["stderr"] == "bad"
    assert result["stderr_lines"] == ["bad"]
    assert result["module_stdout"] == result["stdout"]
    assert result["module_stderr"] == result["stderr"]


# The pseudo-terminal, and what it does to output


def test_the_transport_gets_no_pty_without_become(plugin) -> None:
    """Test a command that does not become asks for no terminal.

    A pseudo-terminal merges stderr into stdout and salts output with
    carriage returns, so it is asked for only when the prompt
    machinery needs it.
    """
    _run(plugin, {"cmd": "echo hi", "raw": True})

    assert _execution(plugin)["sudoable"] is False


def test_become_asks_the_transport_for_a_pty(plugin) -> None:
    """Test become is the one thing that asks for the terminal."""
    plugin._play_context.become = True

    _run(plugin, {"cmd": "echo hi", "raw": True})

    assert _execution(plugin)["sudoable"] is True


def test_carriage_returns_from_a_terminal_are_normalized(plugin) -> None:
    """Test a pseudo-terminal's line endings are normalized away, so
    raw output matches the native module's byte for byte."""
    plugin.transport_answer = _says(stdout="one\r\ntwo\r\n", stderr="bad\r\n")

    result = _run(plugin, {"cmd": "echo hi", "raw": True})

    assert result["stdout"] == "one\ntwo"
    assert result["stdout_lines"] == ["one", "two"]
    assert result["stderr"] == "bad"


def test_the_shared_connection_notice_is_not_the_command_s_stderr(
    plugin,
) -> None:
    """Test the ssh connection's own parting message is stripped, so
    a silent command is not reported as having said something."""
    plugin.transport_answer = _says(
        stderr="Shared connection to host closed.\r\n"
    )

    result = _run(plugin, {"cmd": "echo hi", "raw": True})

    assert result["stderr"] == ""
    assert result["stderr_lines"] == []


def test_strip_empty_ends_false_keeps_the_trailing_newline(plugin) -> None:
    """Test the option that keeps trailing newlines keeps them."""
    plugin.transport_answer = _says(stdout="one\n")

    result = _run(
        plugin,
        {"cmd": "echo one", "strip_empty_ends": False, "raw": True},
    )

    assert result["stdout"] == "one\n"


# What the raw path checks before it runs anything


def test_a_bad_chdir_fails_before_the_command_runs(plugin, tmp_path) -> None:
    """Test a directory the host cannot enter fails the task naming
    it, rather than running the command somewhere else.

    The low level transport has no chdir failure of its own to
    report, so the action checks first.
    """
    with pytest.raises(AnsibleActionFail, match="Unable to change directory"):
        _run(
            plugin,
            {
                "cmd": "echo hi",
                "chdir": str(tmp_path / "absent"),
                "raw": True,
            },
        )

    assert _execution(plugin) is None


def test_chdir_rides_with_the_command(plugin, tmp_path) -> None:
    """Test a directory that is there is handed to the transport."""
    _run(plugin, {"cmd": "echo hi", "chdir": str(tmp_path), "raw": True})

    assert _execution(plugin)["chdir"] == str(tmp_path)


def test_an_executable_without_a_shell_is_dropped(plugin) -> None:
    """Test executable without _uses_shell is dropped with a warning,
    as the builtin command module has done since 2.4."""
    _run(
        plugin,
        {"cmd": "echo hi", "executable": "/bin/bash", "raw": True},
    )

    assert _execution(plugin)["executable"] is None
    plugin._display.warning.assert_called()


def test_stdin_reaches_the_command(plugin) -> None:
    """Test standard input is delivered as bytes, newline terminated,
    which is what a shell heredoc and a native module both give."""
    result = _run(plugin, {"cmd": "cat", "stdin": "hello", "raw": True})

    assert _execution(plugin)["in_data"] == b"hello\n"
    assert result["stdout"] == "hello"


def test_stdin_add_newline_false_sends_what_it_was_given(plugin) -> None:
    """Test the option that suppresses the newline suppresses it."""
    _run(
        plugin,
        {
            "cmd": "cat",
            "stdin": "hello",
            "stdin_add_newline": False,
            "raw": True,
        },
    )

    assert _execution(plugin)["in_data"] == b"hello"


def test_a_non_zero_return_code_is_named(plugin) -> None:
    """Test a command that fails on the raw transport says so, since
    the transport reports the status without judging it."""
    result = _run(plugin, {"cmd": "false", "raw": True})

    assert result["rc"] != 0
    assert result["failed"] is True
    assert result["msg"] == "non-zero return code"
    assert result["changed"] is True


def test_a_zero_return_code_is_not_a_failure(plugin) -> None:
    """Test a raw command that succeeded carries no verdict against
    it, so a caller reading the result reads what happened."""
    result = _run(plugin, {"cmd": "true", "raw": True})

    assert result["rc"] == 0
    assert result["failed"] is False
    assert result["msg"] == ""


def test_both_transports_name_a_failure_alike(plugin) -> None:
    """Test the two transports answer a failed command in one voice.

    The native module fails on a non-zero status and says so in the
    result. The task layer promotes the status on its own afterwards,
    so a task fails either way, but a caller inside this process --
    run's batch is one -- reads the dict and never sees that
    promotion. Both halves of the answer travel on both transports.
    """
    plugin.module_answer = {
        "rc": 1,
        "failed": True,
        "msg": "non-zero return code",
        "stdout": "",
        "stderr": "",
    }

    native = _run(plugin, {"cmd": "false", "raw": False})
    raw = _run(plugin, {"cmd": "false", "raw": True})

    assert native["failed"] is True
    assert raw["failed"] == native["failed"]
    assert raw["msg"] == native["msg"] == "non-zero return code"


def test_a_raw_run_reports_its_timing_as_text(plugin) -> None:
    """Test the timestamps are text by the time they are published,
    since a datetime is not a value a result can carry."""
    result = _run(plugin, {"cmd": "true", "raw": True})

    assert isinstance(result["start"], str)
    assert isinstance(result["end"], str)
    assert isinstance(result["delta"], str)


def test_cmd_and_argv_are_mutually_exclusive(plugin) -> None:
    """Test a command given twice is refused rather than one of the
    two being picked."""
    with pytest.raises(AnsibleActionFail):
        _run(plugin, {"cmd": "echo hi", "argv": ["echo", "hi"]})


def test_a_command_is_required(plugin) -> None:
    """Test a task with nothing to run is refused."""
    with pytest.raises(AnsibleActionFail):
        _run(plugin, {})
