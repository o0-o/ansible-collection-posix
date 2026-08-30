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

"""Unit tests for getent_utils module.

Every fixture here was captured off a running host rather than
written from a manpage, because a manpage is what the getent
question cannot be settled by: the probe has to tell a real getent
from a shell function wearing the name, and only what each of them
actually did settles that.  The captures live beside this file in
``files/`` - one verbatim transcript per platform, holding every
probe's exit status and output as the host gave them.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (
    GETENT_COMMAND_SPEC,
)
from ansible_collections.o0_o.posix.plugins.module_utils.getent_utils import (
    GETENT_RCS,
    _parse_getent,
    get_getent_command_requests,
    process_getent_command_results,
)
from ansible_collections.o0_o.posix.plugins.module_utils.group_utils import (
    group_info,
)
from ansible_collections.o0_o.posix.plugins.module_utils.passwd_utils import (
    passwd_info,
)

FILES = os.path.join(os.path.dirname(__file__), "files")

# The captured platforms whose getent proved to be one. The captures
# that did not - grep_shim and macos - are named where they are tested,
# because what each of them failed on is the point of the test.
REAL_GETENT = ("linux_glibc", "linux_musl", "freebsd14", "openbsd79")

# The ones with no -V, which is three of the four real ones
NO_VERSION_FLAG = ("linux_musl", "freebsd14", "openbsd79")

ENUMERATE = {
    "passwd": "getent passwd (enumerate)",
    "group": "getent group (enumerate)",
}
MISSING_KEY = {
    "passwd": "getent passwd zzznosuchuser42",
    "group": "getent group zzznosuchgroup42",
}
BAD_DATABASE = "getent baddatabase"
VERSION = "getent -V"


def corpus(name: str) -> str:
    """Read a captured fixture verbatim.

    :param str name: File name under ``files/``
    :returns str: The file's contents
    """
    with open(os.path.join(FILES, name), encoding="utf-8") as handle:
        return handle.read()


def probes(platform: str) -> dict[str, dict[str, Any]]:
    """Read one platform's capture into a probe per command.

    :param str platform: The captured platform's name
    :returns dict[str, dict[str, Any]]: Each probe's rc and stdout,
        keyed by the label the capture gave it
    """
    found: dict[str, dict[str, Any]] = {}
    current: Optional[dict[str, Any]] = None
    label = ""
    where = "stdout"

    for line in corpus(f"getent_probe_{platform}.txt").splitlines():
        if line.startswith("===CMD=== "):
            label = line[len("===CMD=== ") :]
            current = {"stdout": [], "stderr": [], "rc": None}
            found[label] = current
            where = "stdout"
        elif current is None:
            continue
        elif line == "---STDERR---":
            where = "stderr"
        elif line.startswith("---RC--- "):
            current["rc"] = int(line[len("---RC--- ") :])
            current = None
        else:
            current[where].append(line)

    return {
        label: {"rc": probe["rc"], "stdout": "\n".join(probe["stdout"])}
        for label, probe in found.items()
    }


def parse(platform: str, database: str) -> Optional[str]:
    """Run the probe over one platform's captured enumeration.

    :param str platform: The captured platform's name
    :param str database: The database enumerated
    :returns Optional[str]: What the parser made of it
    """
    probe = probes(platform)[ENUMERATE[database]]
    parsed, errors = _parse_getent(
        probe["rc"], probe["stdout"], "test: ", database=database
    )
    assert errors is None
    return parsed


@pytest.mark.parametrize("platform", REAL_GETENT)
@pytest.mark.parametrize("database", ["passwd", "group"])
def test_a_real_getent_enumerates_and_is_believed(
    platform: str, database: str
) -> None:
    """Test a getent that enumerated its database is taken for one."""
    probe = probes(platform)[ENUMERATE[database]]

    assert probe["rc"] == 0
    assert parse(platform, database) == probe["stdout"]


@pytest.mark.parametrize("database", ["passwd", "group"])
def test_the_grep_shim_cannot_enumerate_and_is_not_believed(
    database: str,
) -> None:
    """Test the shell function wearing the name is refused.

    zsh's compaudit defines a ``getent`` that greps the flat files on
    hosts having no such binary.  Asked for a whole database it has no
    key to grep with, so it prints nothing and exits 1 - which is the
    discriminator, and the reason the probe asks for an enumeration
    rather than a key.
    """
    probe = probes("grep_shim")[ENUMERATE[database]]

    assert probe["rc"] == 1
    assert probe["stdout"] == ""
    assert parse("grep_shim", database) is None


def test_the_shim_answers_a_key_exactly_as_a_real_getent_would() -> None:
    """Test why a key lookup could not have been the probe.

    Asked for root, the shim prints the same line the real program
    does and exits 0 alongside it.  Anything keyed is common ground
    between the two, so the fingerprint had to be found where they
    differ.
    """
    shim = probes("grep_shim")["getent passwd root"]

    assert shim["rc"] == 0
    assert shim["stdout"].startswith("root:")


def test_the_missing_key_convention_separates_the_families() -> None:
    """Test the exit codes on a key that is not there.

    The real family answers 2 for a key it could not find and 1 for a
    database it does not know; the shim, which is grep, has those the
    other way round, since grep says 1 for no match and 2 for a file
    it could not open.  Corroborating evidence, recorded because it is
    what the ruling asked to see pinned - the probe does not rest on
    it, because an enumeration settles the question one command
    earlier and is the command the gather needs anyway.
    """
    for platform in REAL_GETENT:
        found = probes(platform)
        assert found[MISSING_KEY["passwd"]]["rc"] == 2
        assert found[MISSING_KEY["group"]]["rc"] == 2
        assert found[BAD_DATABASE]["rc"] == 1

    shim = probes("grep_shim")
    assert shim[MISSING_KEY["passwd"]]["rc"] == 1
    assert shim[BAD_DATABASE]["rc"] == 2


def test_openbsd_is_in_the_real_family_after_all() -> None:
    """Test the platform the ruling flagged as the one to check.

    OpenBSD's getent was expected to sit close to the grep shim, and
    on the exit codes it does not: a key it cannot find is 2 and a
    database it does not know is 1, the same convention glibc keeps.
    Where it does resemble the shim is in refusing -V, which is the
    one signal the probe was told not to trust.
    """
    openbsd = probes("openbsd79")

    assert openbsd[MISSING_KEY["passwd"]]["rc"] == 2
    assert openbsd[BAD_DATABASE]["rc"] == 1
    assert openbsd[VERSION]["rc"] == 1
    assert openbsd[ENUMERATE["passwd"]]["rc"] == 0


def test_version_is_a_glibc_marker_not_a_getent_one() -> None:
    """Test -V would have misread three real platforms as having none.

    glibc's getent takes -V and prints a version.  musl's rejects it,
    and so do FreeBSD's and OpenBSD's - three real, enumerating
    getents that a probe resting on -V would have called absent.  It
    is a marker of one libc rather than of the program, which is why
    the ruling refused it and why nothing here asks.
    """
    assert probes("linux_glibc")[VERSION]["rc"] == 0
    assert probes("grep_shim")[VERSION]["rc"] == 2

    for platform in NO_VERSION_FLAG:
        assert probes(platform)[VERSION]["rc"] == 1
        # Whatever -V says, each of them enumerates and is believed
        assert parse(platform, "passwd") is not None


def test_macos_has_no_getent_at_all() -> None:
    """Test the platform the ruling leaves to a future collection.

    Darwin resolves names through Directory Services, which posix
    does not speak and will not learn: no getent is on the host, the
    probe finds nothing, and files-only gathering continues.
    """
    capture = corpus("getent_probe_macos.txt")

    assert "(no getent on PATH)" in capture
    assert "===ABSENT===" in capture
    assert "===CMD===" not in capture


@pytest.mark.parametrize("rc", [1, 2, 126, 127])
@pytest.mark.parametrize("database", ["passwd", "group"])
def test_no_answer_is_ever_an_error(rc: int, database: str) -> None:
    """Test every way of having no getent is quiet.

    A host with no getent, one whose getent is a shim, and one whose
    getent broke are one answer to the composition - nothing to
    overlay - and none of them is a fault to report.
    """
    parsed, errors = _parse_getent(rc, "", "test: ", database=database)

    assert parsed is None
    assert errors is None


@pytest.mark.parametrize("database", ["passwd", "group"])
def test_output_alone_does_not_buy_belief(database: str) -> None:
    """Test rc 0 over something that is not a database is refused."""
    usage = "Usage: getent database [key ...]"

    assert _parse_getent(0, usage, "test: ", database=database) == (None, None)
    assert _parse_getent(0, "   \n", "test: ", database=database) == (
        None,
        None,
    )


def test_the_bsds_drop_the_empty_members_field() -> None:
    """Test the format difference the captures turned up.

    A group nobody is a secondary member of is four fields the last
    of which is empty, and every flat file writes it that way -
    FreeBSD's own /etc/group included.  Its getent does not: both
    BSDs print ``bin:*:7`` where Linux prints ``bin:x:7:``, dropping
    the delimiter with the field.  Before this was captured the
    parser raised on it, which would have read to the caller as a
    BSD that has no getent.
    """
    for platform in ("freebsd14", "openbsd79"):
        lines = probes(platform)[ENUMERATE["group"]]["stdout"].splitlines()
        short = [line for line in lines if line.count(":") == 2]

        assert short, f"{platform} printed no short group line"
        assert parse(platform, "group") is not None

    for platform in ("linux_glibc", "linux_musl"):
        lines = probes(platform)[ENUMERATE["group"]]["stdout"].splitlines()

        assert all(line.count(":") == 3 for line in lines)


def test_every_captured_platform_parses_to_the_same_shape() -> None:
    """Test one composition reads all four real platforms.

    The BSDs write their password field ``*`` where Linux writes
    ``x``, spell their gecos with the ampersand convention, and leave
    off the empty members field.  None of it reaches the fact: every
    platform composes users keyed by uid and groups keyed by gid.
    """
    for platform in REAL_GETENT:
        users = passwd_info(parse(platform, "passwd"), key="id")
        groups = group_info(parse(platform, "group"), key="id")

        assert users["0"]["name"] in ("root", "toor")
        assert groups["0"]["name"] in ("root", "wheel")
        assert all(uid.isdigit() for uid in users)
        assert all(gid.isdigit() for gid in groups)
        assert all(
            isinstance(group["members"], list) for group in groups.values()
        )


def test_the_spec_treats_every_plausible_status_as_an_answer() -> None:
    """Test the parser, not the runner, is what decides."""
    for request in get_getent_command_requests():
        assert request["non_error_codes"] == GETENT_RCS
        assert 127 in request["non_error_codes"]
        assert request["parser"] is _parse_getent

    assert set(GETENT_COMMAND_SPEC["posix"]) == {
        "getent_passwd",
        "getent_group",
    }


def test_the_probe_is_the_gather() -> None:
    """Test one enumeration per database, and nothing besides.

    The fingerprint costs no command of its own: what proves the
    candidate is a getent is the same output the composition
    overlays.
    """
    requests = get_getent_command_requests()

    assert len(requests) == 2
    assert [request["command"] for request in requests] == [
        ("getent", "passwd"),
        ("getent", "group"),
    ]


def _answer(request: dict[str, Any], platform: str) -> dict[str, Any]:
    """Dress a request in one platform's captured answer.

    :param dict[str, Any] request: The command request
    :param str platform: The captured platform's name
    :returns dict[str, Any]: The completed command
    """
    database = request["type"].split("_", 1)[1]
    probe = probes(platform)[ENUMERATE[database]]

    return dict(
        request,
        rc=probe["rc"],
        stdout=probe["stdout"],
        stdout_lines=probe["stdout"].splitlines(),
        stderr="",
        stderr_lines=[],
    )


@pytest.mark.parametrize("platform", REAL_GETENT)
def test_processing_answers_per_database(platform: str) -> None:
    """Test the batch's results read back as one entry per database."""
    resolved = process_getent_command_results(
        [
            _answer(request, platform)
            for request in get_getent_command_requests()
        ]
    )

    assert set(resolved) == {"passwd", "group"}
    # Every POSIX host has a uid 0 and a gid 0, whatever it calls the
    # group - Linux says root and the BSDs say wheel
    assert "0" in passwd_info(resolved["passwd"], key="id")
    assert "0" in group_info(resolved["group"], key="id")


def test_processing_a_host_without_getent_answers_none() -> None:
    """Test absence arrives as a complete answer, not a silence.

    A caller composing with this never asks whether the host has
    getent; it asks what getent said, and None says it.
    """
    answers = [
        dict(
            request,
            rc=127,
            stdout="",
            stdout_lines=[],
            stderr="sh: getent: not found",
            stderr_lines=["sh: getent: not found"],
        )
        for request in get_getent_command_requests()
    ]

    assert process_getent_command_results(answers) == {
        "passwd": None,
        "group": None,
    }


def test_processing_a_batch_that_never_ran_getent_answers_none() -> None:
    """Test a result set missing the probes entirely is not a crash."""
    assert process_getent_command_results([]) == {
        "passwd": None,
        "group": None,
    }
