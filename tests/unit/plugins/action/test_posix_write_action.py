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

"""Unit tests for the write action plugin's family dispatch."""

from __future__ import annotations

import re
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from ansible.errors import AnsibleActionFail
from ansible_collections.o0_o.posix.plugins.action.write import ActionModule

# The permission dictionary the plugin hands to the write machinery
# when a task names no owner, group, mode, or SELinux context
NO_PERMS = {
    "owner": None,
    "group": None,
    "mode": None,
    "selevel": None,
    "serole": None,
    "setype": None,
    "seuser": None,
}


class RecordingWriteAction(ActionModule):
    """A write ActionModule whose transport seams are recorded.

    Every method overridden here is a boundary the plugin crosses to
    reach the remote host. Tests program what the host reports back
    through ``stats``, ``payloads``, and ``command_results``, then read
    what the plugin sent out of ``commands``, ``reads``, ``writes``,
    ``mkdirs``, and ``dest_dirs``. Argument validation, family
    resolution, and the editing engines all run for real.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.stats: dict[str, dict[str, Any]] = {}
        self.payloads: dict[str, dict[str, Any]] = {}
        self.command_results: list[dict[str, Any]] = []
        self.commands: list[Any] = []
        self.reads: list[tuple[Any, dict[str, Any]]] = []
        self.writes: list[dict[str, Any]] = []
        self.mkdirs: list[str] = []
        self.dest_dirs: list[str] = []
        self.write_result: dict[str, Any] = {
            "changed": True,
            "msg": "File written successfully",
            "rc": 0,
        }

    def _pseudo_stat(
        self,
        target_path: str,
        task_vars: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Report the stat the test programmed for this path."""
        return self.stats.get(
            target_path, {"exists": False, "type": None, "raw": False}
        )

    def _read(
        self,
        paths: Any,
        task_vars: Optional[dict[str, Any]] = None,
        check_mode: Optional[bool] = None,
        **options: Any,
    ) -> dict[str, Any]:
        """Record the read request and return the programmed payload."""
        self.reads.append((paths, options))
        return {"paths": {paths: self.payloads[paths]}}

    def _write_file(
        self,
        content: Any,
        dest: str,
        perms: Optional[dict[str, Any]] = None,
        backup: bool = False,
        validate_cmd: Optional[str] = None,
        check_mode: Optional[bool] = None,
        task_vars: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Record the write request and report it succeeded."""
        self.writes.append(
            {
                "content": content,
                "dest": dest,
                "perms": perms,
                "backup": backup,
                "validate_cmd": validate_cmd,
                "check_mode": check_mode,
            }
        )
        return dict(self.write_result)

    def _command(
        self,
        cmd: Any,
        task_vars: Optional[dict[str, Any]] = None,
        check_mode: Optional[bool] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Record the command and return the next programmed result."""
        self.commands.append(cmd)
        if self.command_results:
            return self.command_results.pop(0)
        return {"rc": 0, "stdout": "", "stderr": ""}

    def _mkdir(
        self,
        target_path: str,
        task_vars: Optional[dict[str, Any]] = None,
        parents: Optional[bool] = True,
        mode: Optional[str] = None,
    ) -> dict[str, Any]:
        """Record the directory creation."""
        self.mkdirs.append(target_path)
        return {"changed": True}

    def _mk_dest_dir(
        self,
        file_path: str,
        task_vars: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record that the destination's parent was ensured."""
        self.dest_dirs.append(file_path)


@pytest.fixture
def plugin() -> RecordingWriteAction:
    """Create a write ActionModule with recorded transport seams."""

    task = MagicMock()
    task.async_val = 0
    task.check_mode = False
    task.args = {}

    connection = MagicMock()
    connection._shell.tmpdir = "/tmp/ansible-tmp-write"

    action = RecordingWriteAction(
        task=task,
        connection=connection,
        play_context=MagicMock(),
        loader=MagicMock(),
        templar=MagicMock(),
        shared_loader_obj=MagicMock(),
    )
    action._display = MagicMock()
    action.inventory_hostname = "localhost"

    return action


# Family resolution


@pytest.mark.parametrize(
    "args, expected_family",
    [
        ({"dest": "/etc/foo", "content": "hi"}, "content"),
        ({"dest": "/etc/foo", "src": "foo.txt"}, "src"),
        ({"dest": "/etc/foo", "template": "foo.j2"}, "template"),
        ({"dest": "/etc/foo", "line": "x"}, "line"),
        ({"dest": "/etc/foo", "block": "x"}, "block"),
        ({"dest": "/etc/dir", "state": "directory"}, "state"),
        ({"dest": "/etc/foo", "state": "absent"}, "state"),
        ({"dest": "/etc/foo", "state": "touch"}, "state"),
        (
            {"dest": "/etc/link", "state": "link", "target": "/etc/foo"},
            "state",
        ),
        # A line edit keeps its family when it removes rather than adds
        ({"dest": "/etc/foo", "line": "x", "state": "absent"}, "line"),
        # The aliases select the same families
        ({"path": "/etc/foo", "content": "hi"}, "content"),
        ({"name": "/etc/foo", "value": "x"}, "line"),
    ],
)
def test_resolve_family(plugin, args, expected_family) -> None:
    """Test the canary argument selects the operation family."""

    plugin._task.args = dict(args)

    assert plugin._resolve_family(plugin._def_args()) == expected_family


@pytest.mark.parametrize(
    "args, expected_error",
    [
        # Two canaries at once
        (
            {"dest": "/etc/foo", "content": "a", "line": "b"},
            "parameters are mutually exclusive: "
            "content|src|template|line|block",
        ),
        # No canary and no bare state to fall back on
        (
            {"dest": "/etc/foo"},
            "one of content, src, template, line, or block is required "
            "with state=present",
        ),
        # A content family cannot carry a bare state
        (
            {"dest": "/etc/foo", "content": "a", "state": "directory"},
            "content requires state=present, got state=directory",
        ),
        # A link needs somewhere to point
        (
            {"dest": "/etc/link", "state": "link"},
            "state is link but all of the following are missing: target",
        ),
    ],
)
def test_resolve_family_rejects(plugin, args, expected_error) -> None:
    """Test an unusable argument set fails before any host work."""

    plugin._task.args = dict(args)

    with pytest.raises(AnsibleActionFail, match=re.escape(expected_error)):
        plugin._resolve_family(plugin._def_args())

    assert plugin.commands == []
    assert plugin.writes == []


# Line family argument audits


def test_audit_line_args_requires_regexp_with_backrefs(plugin) -> None:
    """Test backrefs without a regexp fails the task."""

    plugin._task.args = {"dest": "/etc/foo", "line": "x", "backrefs": True}

    with pytest.raises(
        AnsibleActionFail, match="regexp is required with backrefs=true"
    ):
        plugin._audit_line_args(plugin._def_args())


@pytest.mark.parametrize(
    "args, expected_fragments",
    [
        (
            {"dest": "/etc/foo", "line": "x", "regexp": ""},
            [
                "[localhost] The regular expression is an empty string",
                "use '^' to match every line",
            ],
        ),
        (
            {"dest": "/etc/foo", "line": "x", "search_string": ""},
            ["[localhost] The search string is an empty string"],
        ),
    ],
)
def test_audit_line_args_warns_on_empty_pattern(
    plugin, args, expected_fragments
) -> None:
    """Test an empty match pattern warns that it matches everything."""

    plugin._task.args = dict(args)

    plugin._audit_line_args(plugin._def_args())

    plugin._display.warning.assert_called_once()
    warning = plugin._display.warning.call_args[0][0]
    for fragment in expected_fragments:
        assert fragment in warning


# Dispatch


def test_content_family_writes_the_literal_content(plugin) -> None:
    """Test the content family writes its content unchanged."""

    plugin._task.args = {
        "dest": "/etc/foo",
        "content": "hello\nworld\n",
        "mode": "0644",
        "backup": True,
    }

    result = plugin.run(task_vars={})

    assert plugin.dest_dirs == ["/etc/foo"]
    assert plugin.writes == [
        {
            "content": "hello\nworld\n",
            "dest": "/etc/foo",
            "perms": dict(NO_PERMS, mode="0644"),
            "backup": True,
            "validate_cmd": None,
            "check_mode": False,
        }
    ]
    assert result["changed"] is True
    assert result["msg"] == "File written successfully"


def test_line_family_writes_the_edited_lines(plugin) -> None:
    """Test the line family edits the lines it read from the dest."""

    plugin.stats["/etc/hosts"] = {
        "exists": True,
        "type": "file",
        "raw": False,
    }
    plugin.payloads["/etc/hosts"] = {
        "lines": ["127.0.0.1 localhost", "10.0.0.1 db", "127.0.0.1 localhost"]
    }
    plugin._task.args = {
        "dest": "/etc/hosts",
        "line": "127.0.0.1 localhost",
    }

    result = plugin.run(task_vars={})

    assert plugin.reads == [("/etc/hosts", {"content": True, "lines": True})]
    assert plugin.writes[0]["content"] == [
        "10.0.0.1 db",
        "127.0.0.1 localhost",
    ]
    assert plugin.writes[0]["dest"] == "/etc/hosts"
    assert result["msg"] == "1 line deduped"


def test_line_family_splits_content_when_lines_are_absent(plugin) -> None:
    """Test the line family falls back to splitting the read content."""

    plugin.stats["/etc/hosts"] = {
        "exists": True,
        "type": "file",
        "raw": False,
    }
    plugin.payloads["/etc/hosts"] = {"content": "alpha\nbeta\n"}
    plugin._task.args = {"dest": "/etc/hosts", "line": "gamma"}

    plugin.run(task_vars={})

    assert plugin.writes[0]["content"] == ["alpha", "beta", "gamma"]


def test_line_family_removes_lines_when_absent(plugin) -> None:
    """Test state=absent on a line edit removes every match."""

    plugin.stats["/etc/hosts"] = {
        "exists": True,
        "type": "file",
        "raw": False,
    }
    plugin.payloads["/etc/hosts"] = {"lines": ["a", "b", "a"]}
    plugin._task.args = {
        "dest": "/etc/hosts",
        "line": "a",
        "state": "absent",
    }

    result = plugin.run(task_vars={})

    assert plugin.writes[0]["content"] == ["b"]
    assert result["found"] == 2
    assert result["msg"] == "2 line(s) removed"


def test_line_family_requires_the_dest_without_create(plugin) -> None:
    """Test a missing destination fails unless create is set."""

    plugin._task.args = {"dest": "/etc/gone", "line": "x"}

    with pytest.raises(
        AnsibleActionFail, match="Destination /etc/gone does not exist!"
    ):
        plugin.run(task_vars={})

    assert plugin.writes == []


def test_line_family_starts_empty_with_create(plugin) -> None:
    """Test create lets a line edit build the file from nothing."""

    plugin._task.args = {"dest": "/etc/new", "line": "x", "create": True}

    plugin.run(task_vars={})

    assert plugin.reads == []
    assert plugin.writes[0]["content"] == ["x"]


def test_block_family_writes_the_marked_block(plugin) -> None:
    """Test the block family appends its block between markers."""

    plugin.stats["/etc/hosts"] = {
        "exists": True,
        "type": "file",
        "raw": False,
    }
    plugin.payloads["/etc/hosts"] = {"lines": ["head", "tail"]}
    plugin._task.args = {"dest": "/etc/hosts", "block": "x\ny"}

    result = plugin.run(task_vars={})

    assert plugin.writes[0]["content"] == [
        "head",
        "tail",
        "# BEGIN ANSIBLE MANAGED BLOCK",
        "x",
        "y",
        "# END ANSIBLE MANAGED BLOCK",
    ]
    assert result["msg"] == "block added"


def test_line_family_surfaces_engine_errors(plugin) -> None:
    """Test an unusable pattern fails the task instead of raising."""

    plugin.stats["/etc/hosts"] = {
        "exists": True,
        "type": "file",
        "raw": False,
    }
    plugin.payloads["/etc/hosts"] = {"lines": ["a"]}
    plugin._task.args = {
        "dest": "/etc/hosts",
        "line": "b",
        "regexp": "[",
    }

    with pytest.raises(
        AnsibleActionFail, match=re.escape("Invalid regexp pattern: [")
    ):
        plugin.run(task_vars={})

    assert plugin.writes == []


@pytest.mark.parametrize(
    "path_type, expected_argv",
    [
        ("file", ["rm", "-f", "/etc/foo"]),
        ("directory", ["rm", "-rf", "/etc/foo"]),
    ],
)
def test_absent_removes_an_existing_path(
    plugin, path_type, expected_argv
) -> None:
    """Test state=absent removes what is there and says so."""

    plugin.stats["/etc/foo"] = {
        "exists": True,
        "type": path_type,
        "raw": False,
    }
    plugin._task.args = {"dest": "/etc/foo", "state": "absent"}

    result = plugin.run(task_vars={})

    assert plugin.commands == [expected_argv]
    assert result["changed"] is True
    assert result["msg"] == "path removed"


def test_absent_on_a_missing_path_does_nothing(plugin) -> None:
    """Test state=absent on a missing path issues no commands."""

    plugin._task.args = {"dest": "/etc/gone", "state": "absent"}

    result = plugin.run(task_vars={})

    assert plugin.commands == []
    assert result["changed"] is False
    assert result["msg"] == "path already absent"


def test_absent_reports_a_failed_removal(plugin) -> None:
    """Test a failing rm fails the task with the host's stderr."""

    plugin.stats["/etc/foo"] = {
        "exists": True,
        "type": "file",
        "raw": False,
    }
    plugin.command_results = [
        {"rc": 1, "stdout": "", "stderr": "Permission denied"}
    ]
    plugin._task.args = {"dest": "/etc/foo", "state": "absent"}

    with pytest.raises(
        AnsibleActionFail,
        match="Failed to remove /etc/foo: Permission denied",
    ):
        plugin.run(task_vars={})


def test_link_creates_the_symlink(plugin) -> None:
    """Test state=link points the destination at the target."""

    plugin._task.args = {
        "dest": "/etc/link",
        "state": "link",
        "target": "/etc/foo",
    }

    plugin.command_results = [{"rc": 1, "stdout": "", "stderr": ""}]

    result = plugin.run(task_vars={})

    assert plugin.commands == [
        ["test", "-L", "/etc/link"],
        ["ln", "-sfn", "/etc/foo", "/etc/link"],
    ]
    assert result["changed"] is True
    assert result["msg"] == "link created"


def test_link_leaves_a_correct_symlink_alone(plugin) -> None:
    """Test a link already pointing at the target is not rewritten."""

    plugin.stats["/etc/link"] = {
        "exists": True,
        "type": "file",
        "is_symlink": True,
        "raw": False,
    }
    plugin.command_results = [
        {"rc": 0, "stdout": "", "stderr": ""},
        {"rc": 0, "stdout": "/etc/foo\n", "stderr": ""},
    ]
    plugin._task.args = {
        "dest": "/etc/link",
        "state": "link",
        "target": "/etc/foo",
    }

    result = plugin.run(task_vars={})

    assert plugin.commands == [
        ["test", "-L", "/etc/link"],
        ["readlink", "/etc/link"],
    ]
    assert result["changed"] is False
    assert result["msg"] == "link already points at target"


def test_touch_creates_a_missing_file(plugin) -> None:
    """Test state=touch creates the file when it is missing."""

    plugin._task.args = {"dest": "/etc/foo", "state": "touch"}

    result = plugin.run(task_vars={})

    assert plugin.commands == [["touch", "/etc/foo"]]
    assert result["changed"] is True
    assert result["msg"] == "file created"


def test_directory_creates_a_missing_directory(plugin) -> None:
    """Test state=directory creates the directory when missing."""

    plugin._task.args = {"dest": "/etc/dir", "state": "directory"}

    result = plugin.run(task_vars={})

    assert plugin.mkdirs == ["/etc/dir"]
    assert result["changed"] is True
    assert result["msg"] == "directory created"


@pytest.mark.parametrize(
    "args, stats, expected_msg",
    [
        (
            {"dest": "/etc/foo", "state": "absent"},
            {"/etc/foo": {"exists": True, "type": "file", "raw": False}},
            "Check mode: path would have been removed.",
        ),
        (
            {"dest": "/etc/dir", "state": "directory"},
            {},
            "Check mode: directory would have been created.",
        ),
        (
            {"dest": "/etc/foo", "state": "touch"},
            {},
            "Check mode: file would have been created.",
        ),
        (
            {"dest": "/etc/link", "state": "link", "target": "/etc/foo"},
            {},
            "Check mode: link would have been created.",
        ),
    ],
)
def test_check_mode_reports_without_mutating(
    plugin, args, stats, expected_msg
) -> None:
    """Test check mode reports the change without mutating commands."""

    plugin._task.check_mode = True
    plugin.stats.update(stats)
    plugin._task.args = dict(args)

    result = plugin.run(task_vars={})

    # Read-only probes (test, readlink) are legitimate in check mode
    mutating = [c for c in plugin.commands if c[0] not in ("test", "readlink")]
    assert result["changed"] is True
    assert result["msg"] == expected_msg
    assert mutating == []
    assert plugin.mkdirs == []


def test_force_false_leaves_an_existing_dest_alone(plugin) -> None:
    """Test force=false skips the write when the dest exists."""

    plugin.stats["/etc/foo"] = {
        "exists": True,
        "type": "file",
        "raw": False,
    }
    plugin._task.args = {
        "dest": "/etc/foo",
        "content": "hi",
        "force": False,
    }

    result = plugin.run(task_vars={})

    assert plugin.writes == []
    assert plugin.dest_dirs == []
    assert result["changed"] is False
    assert result["msg"] == (
        "File exists and force is disabled, taking no action"
    )


@pytest.mark.parametrize(
    "raw, expected_mode, expected_report",
    [
        ("auto", "auto", False),
        (True, True, True),
        (False, False, False),
        ("yes", True, True),
    ],
)
def test_raw_arg_accepted(plugin, raw, expected_mode, expected_report) -> None:
    """Test raw accepts 'auto' or a boolean and reports the mode."""

    plugin._task.args = {"dest": "/etc/foo", "content": "hi", "raw": raw}

    result = plugin.run(task_vars={})

    assert plugin.raw == expected_mode
    assert result["raw"] is expected_report


def test_raw_arg_rejects_an_unusable_value(plugin) -> None:
    """Test an uninterpretable raw value fails the task."""

    plugin._task.args = {
        "dest": "/etc/foo",
        "content": "hi",
        "raw": "bogus",
    }

    with pytest.raises(
        AnsibleActionFail, match="Unable to interpret 'bogus' as boolean"
    ):
        plugin.run(task_vars={})

    assert plugin.writes == []
