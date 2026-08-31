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

"""Unit tests for the shared provenance vocabulary."""

from __future__ import annotations

from ansible_collections.o0_o.posix.plugins.module_utils.evidence_utils import (  # noqa: E501
    EVIDENCE_KINDS,
    command_name,
    commands_run,
    compose_evidence,
    merge_entry,
    merge_evidence,
)


def test_the_vocabulary_is_three_kinds() -> None:
    """Test the registry names the whole vocabulary, so a producer
    with something that is none of these has a finding rather than an
    origin and knows it."""
    assert EVIDENCE_KINDS == ("files", "commands", "config")


def test_a_command_is_named_not_spelled_out() -> None:
    """Test argv's first word is the command and the rest is what it
    was asked, which the fact itself answers."""
    assert command_name(("getconf", "_XOPEN_UNIX")) == "getconf"
    assert command_name(["command", "-v", "pax"]) == "command"
    assert command_name(("sh", "-c", 'x=1; [ "$x" = 1 ]')) == "sh"


def test_a_command_found_at_a_path_is_named_by_what_it_is() -> None:
    """Test a probe that resolved to a path is filed under the command
    it is rather than under where the host keeps it."""
    assert command_name(("/usr/bin/getconf", "ARG_MAX")) == "getconf"


def test_a_command_written_as_a_string_names_nothing() -> None:
    """Test a string command is a shell reading it back rather than a
    command being run, so it names nothing here and the producer that
    ran it names what it ran."""
    assert command_name("set -eu; printf '%s' \"${HOME}\"") is None
    assert command_name(None) is None
    assert command_name(()) is None


def test_a_kind_attempted_and_a_kind_absent_are_different() -> None:
    """Test an empty collection says the kind was attempted and
    answered for nothing, and a kind not passed at all is one this
    producer does not have."""
    record = compose_evidence(files=[], commands=["getent"])

    assert record == {"files": [], "commands": ["getent"]}
    assert "config" not in record


def test_a_kind_holds_one_of_each_name_sorted() -> None:
    """Test the same command consulted many times is named once."""
    assert compose_evidence(
        commands=["getconf", "command", "getconf", None]
    ) == {"commands": ["command", "getconf"]}


def test_what_ran_is_read_off_the_batch() -> None:
    """Test a producer names the request types it owns and reads back
    what actually ran for them, so what a fact says was consulted
    cannot drift from what the command spec asks for."""
    batch = [
        {"type": "mount", "command": ("mount",)},
        {"type": "df", "command": ("df", "-P")},
        {"type": "uname", "command": ("uname", "-a")},
    ]

    assert commands_run(batch, "df", "mount") == ["df", "mount"]
    assert commands_run(batch, "uname") == ["uname"]
    assert commands_run(batch) == []


def test_evidence_accumulates_rather_than_being_replaced() -> None:
    """Test two producers that answered for one entry both stay in it,
    because an entry claiming half of what put it there is wrong about
    where it came from."""
    into = {"commands": ["uname"], "config": {"ARG_MAX": 1}}
    merge_evidence(into, {"commands": ["date"], "config": {"OPEN_MAX": 2}})

    assert into == {
        "commands": ["date", "uname"],
        "config": {"ARG_MAX": 1, "OPEN_MAX": 2},
    }


def test_a_variable_read_twice_keeps_the_first_answer() -> None:
    """Test a variable read twice in one gather was read from one
    host, so the second reading does not overwrite the first."""
    into = {"config": {"_XOPEN_UNIX": 1}}
    merge_evidence(into, {"config": {"_XOPEN_UNIX": 0}})

    assert into == {"config": {"_XOPEN_UNIX": 1}}


def test_a_kind_the_other_record_alone_has_is_gained() -> None:
    """Test merging a kind the receiving record does not carry adds
    it, so a producer that reads files can fold into one that ran a
    command."""
    into = {"commands": ["getent"]}
    merge_evidence(into, {"files": ["/etc/passwd"]})

    assert into == {"commands": ["getent"], "files": ["/etc/passwd"]}


def test_a_later_producer_wins_every_field_but_provenance() -> None:
    """Test a merge means the later producer's answer, except for
    where the answers came from: both producers belong there."""
    into = {
        "uid": 0,
        "shell": "/bin/sh",
        "evidence": {"files": ["/etc/passwd"], "commands": []},
    }
    merge_entry(
        into,
        {"shell": "/bin/zsh", "evidence": {"commands": ["id", "sh"]}},
    )

    assert into == {
        "uid": 0,
        "shell": "/bin/zsh",
        "evidence": {"files": ["/etc/passwd"], "commands": ["id", "sh"]},
    }


def test_an_entry_with_no_provenance_merges_as_it_always_did() -> None:
    """Test an entry that names no origins is merged whole, so nothing
    has to carry evidence to take part in a merge."""
    into = {"uid": 0}
    merge_entry(into, {"locale": "en_US.UTF-8"})

    assert into == {"uid": 0, "locale": "en_US.UTF-8"}
