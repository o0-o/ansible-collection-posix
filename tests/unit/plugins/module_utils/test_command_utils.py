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

"""Unit tests for the o0_paths observation command lookups compose."""

from __future__ import annotations

from typing import Any, Optional

from ansible_collections.o0_o.posix.plugins.module_utils.command_utils import (
    ANSWERING_SHELL,
    process_command_lookups,
)

INFERRED = {"executable": True, "executable_evidence": "inferred"}


def _lookup(cmd: str, parsed: Optional[str]) -> dict[str, Any]:
    """Fabricate one ``command -v`` result.

    :param str cmd: The command that was looked up
    :param Optional[str] parsed: What the lookup parsed out, or None
        where the command did not resolve
    :returns dict[str, Any]: A lookup_command result
    """
    return {"args": {"cmd": cmd}, "parsed": parsed}


def test_a_resolution_files_under_the_path_it_resolved_to() -> None:
    """Test the fact is about the file, not about the name asked for."""

    paths, missing, errors = process_command_lookups(
        [_lookup("awk", "/usr/bin/awk")]
    )

    assert paths["/usr/bin/awk"] == INFERRED
    assert missing == []
    assert errors == []


def test_the_executable_claim_names_where_it_came_from() -> None:
    """Test a lookup's claim is marked as inferred, leaving a probe of
    the mode free to say something else without the two blending."""

    paths, _, _ = process_command_lookups([_lookup("awk", "/usr/bin/awk")])

    assert paths["/usr/bin/awk"]["executable_evidence"] == "inferred"


def test_a_miss_files_null_at_each_candidate_path() -> None:
    """Test a command the lookups did not find is confirmed absent at
    its name in every directory they searched, which the resolutions
    themselves are the evidence for."""

    paths, missing, _ = process_command_lookups(
        [
            _lookup("awk", "/usr/bin/awk"),
            _lookup("tar", "/bin/tar"),
            _lookup("pax", None),
        ]
    )

    assert paths["/usr/bin/pax"] is None
    assert paths["/bin/pax"] is None
    assert missing == ["pax"]


def test_a_miss_names_no_candidate_without_a_resolution() -> None:
    """Test a sweep that resolved nothing searched no directory it can
    name, so its misses file nothing rather than a guess."""

    paths, missing, _ = process_command_lookups([_lookup("pax", None)])

    assert set(paths) == {ANSWERING_SHELL}
    assert missing == ["pax"]


def test_a_name_that_cannot_be_a_file_names_no_candidate() -> None:
    """Test a dot is not a filename, so a shell that fails to report it
    leaves no '/usr/bin/.' behind for the store to refuse."""

    paths, missing, errors = process_command_lookups(
        [_lookup("awk", "/usr/bin/awk"), _lookup(".", None)]
    )

    assert "/usr/bin/." not in paths
    assert missing == ["."]
    assert errors == []


def test_builtins_and_aliases_file_on_the_shell_that_answered() -> None:
    """Test the shell's own entry carries what the shell said about
    itself, sorted, rather than a namespace of its own."""

    paths, _, _ = process_command_lookups(
        [
            _lookup("cd", "cd"),
            _lookup("[", "["),
            _lookup("ls", "alias ls='ls --color=auto'"),
        ]
    )

    assert paths[ANSWERING_SHELL] == {
        "aliases": {"ls": "ls --color=auto"},
        "builtins": ["[", "cd"],
    }


def test_the_shell_entry_is_whole_where_sh_resolved_to_it() -> None:
    """Test one path observed twice by one producer is composed once,
    since the store replaces an entry rather than blending fields."""

    paths, _, _ = process_command_lookups(
        [_lookup("sh", ANSWERING_SHELL), _lookup("cd", "cd")]
    )

    assert paths[ANSWERING_SHELL] == {
        "executable": True,
        "executable_evidence": "inferred",
        "aliases": {},
        "builtins": ["cd"],
    }


def test_the_shell_answered_even_where_sh_did_not_resolve() -> None:
    """Test the shell that ran the probes is not filed as absent by
    the miss of the name it happens to share."""

    paths, missing, _ = process_command_lookups(
        [_lookup("cat", "/bin/cat"), _lookup("sh", None)]
    )

    assert paths[ANSWERING_SHELL] == {"aliases": {}, "builtins": []}
    assert missing == ["sh"]


def test_a_missing_command_utility_stops_the_lookups() -> None:
    """Test nothing else is trusted once command itself is missing, and
    the shell still publishes the nothing it answered with."""

    paths, missing, errors = process_command_lookups(
        [_lookup("command", None), _lookup("awk", "/usr/bin/awk")]
    )

    assert missing == ["command"]
    assert paths == {ANSWERING_SHELL: {"aliases": {}, "builtins": []}}
    assert errors == []


def test_unexpected_lookup_output_is_an_error() -> None:
    """Test output that is neither a path, an alias nor the name back
    is reported rather than filed as a fact."""

    paths, missing, errors = process_command_lookups(
        [_lookup("awk", "no idea what awk is")]
    )

    assert missing == []
    assert paths == {ANSWERING_SHELL: {"aliases": {}, "builtins": []}}
    assert len(errors) == 1
    assert "Unexpected 'command -v awk' output" in str(errors[0])


def test_a_path_the_store_refuses_does_not_take_the_sweep_down() -> None:
    """Test a host whose PATH doubles a separator loses that one entry
    to an error, not the whole observation. The store keys a path one
    way, and repairing the answer here would key it two."""

    paths, _, errors = process_command_lookups(
        [_lookup("awk", "/usr/bin//awk"), _lookup("cat", "/bin/cat")]
    )

    assert paths["/bin/cat"] == INFERRED
    assert "/usr/bin//awk" not in paths
    assert len(errors) == 1
    assert "empty path component" in str(errors[0])
