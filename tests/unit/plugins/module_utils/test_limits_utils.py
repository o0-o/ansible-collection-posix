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

"""Unit tests for limits_utils module.

Every fixture here was captured off a running shell rather than
written from a manpage, because ``ulimit -a`` has no specified output
and five shells print five formats.  Three of the captures are the
``/bin/sh`` of a platform this collection supports; the other two are
shells a user may log in with, which is what the shell-context probes
ask.  What each of them actually printed is the only thing that
settles whether one parser reads them all.
"""

from __future__ import annotations

import os

from typing import Any

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (
    LIMITS_COMMAND_SPEC,
)
from ansible_collections.o0_o.posix.plugins.module_utils.limits_utils import (
    _parse_ulimit,
    _parse_umask,
    get_limits_command_requests,
    process_limits_command_results,
)

FILES = os.path.join(os.path.dirname(__file__), "files")

# Every captured shell, and the format each of them prints.  macOS's
# /bin/sh labels the unit and the option together; ash labels the unit
# alone; dash glues the unit to the label with no space; ksh puts the
# option in a column of its own and says "not supported" where it will
# not answer; zsh leads with the option and a colon.
SHELLS = (
    "linux_glibc",
    "linux_musl",
    "macos",
    "macos_ksh",
    "macos_zsh",
)

# The three shells of one machine, which have to agree about it
MACOS_SHELLS = ("macos", "macos_ksh", "macos_zsh")

# What every capture names, whatever it calls it
UNIVERSAL = (
    "core",
    "cpu_time",
    "data",
    "file_size",
    "open_files",
    "processes",
    "stack",
    "virtual_memory",
)


def corpus(name: str) -> str:
    """Read a captured fixture verbatim.

    :param str name: File name under ``files/``
    :returns str: The file's contents
    """
    with open(os.path.join(FILES, name), encoding="utf-8") as handle:
        return handle.read()


def limits(shell: str) -> dict[str, Any]:
    """Parse one captured shell's probe output.

    :param str shell: The captured shell's name
    :returns dict[str, Any]: The limits keyed by resource
    """
    parsed, errors = _parse_ulimit(corpus(f"ulimit_{shell}.txt"), "test: ")
    assert errors is None
    return parsed


@pytest.mark.parametrize("shell", SHELLS)
def test_every_shells_format_reads_into_one_shape(shell: str) -> None:
    """Test one parser reads all five formats."""
    parsed = limits(shell)

    for resource in UNIVERSAL:
        assert resource in parsed, shell
        assert set(parsed[resource]) <= {"soft", "hard", "unit"}
        for ceiling in ("soft", "hard"):
            value = parsed[resource][ceiling]
            assert value is None or isinstance(value, int)
            assert not isinstance(value, bool)


@pytest.mark.parametrize("shell", SHELLS)
def test_a_resource_is_named_rather_than_lettered(shell: str) -> None:
    """Test no resource is keyed by an option letter.

    The letters are not portable - ``-p`` is the pipe buffer under
    bash and the process count under dash - so a fact keyed by one
    would file two resources under a single name.
    """
    for resource in limits(shell):
        assert len(resource) > 1
        assert not resource.startswith("-")


def test_three_shells_of_one_machine_agree_about_it() -> None:
    """Test the parse is of the machine, not of the shell.

    All three were captured moments apart on one host as one user, so
    a resource all three named has to carry one answer, whatever each
    of them called it and whichever column it printed it in.
    """
    parsed = {shell: limits(shell) for shell in MACOS_SHELLS}
    shared = set.intersection(*(set(answer) for answer in parsed.values()))

    assert UNIVERSAL[0] in shared

    for resource in shared:
        ceilings = {
            shell: (
                answer[resource]["soft"],
                answer[resource]["hard"],
            )
            for shell, answer in parsed.items()
        }
        assert len(set(ceilings.values())) == 1, (resource, ceilings)


def test_unlimited_is_a_ceiling_and_not_supported_is_not() -> None:
    """Test the two ways a shell declines to name a number differ.

    A resource with no cap is present and null. A resource the shell
    says it does not support is absent, because refusing to answer is
    not the same as answering that there is no limit.
    """
    parsed = limits("macos_ksh")

    # ksh prints "unlimited" for these, and "not supported" for locks,
    # message queues, nice, rtprio, swap and threads
    assert parsed["cpu_time"]["soft"] is None
    assert parsed["cpu_time"]["hard"] is None

    for resource in (
        "file_locks",
        "message_queues",
        "scheduling_priority",
        "realtime_priority",
        "swap",
        "threads",
    ):
        assert resource not in parsed


def test_the_unit_the_shell_reported_is_kept() -> None:
    """Test a number arrives with the unit that makes it readable.

    The same resource is stack size in kbytes to one shell and
    Kibytes to another, so the unit travels with the number rather
    than being assumed by whoever reads it.
    """
    assert limits("macos")["stack"]["unit"] == "kbytes"
    assert limits("macos_ksh")["stack"]["unit"] == "Kibytes"
    assert limits("linux_musl")["stack"]["unit"] == "kb"

    # A label with no parenthetical carries no unit rather than a
    # guessed one
    assert "unit" not in limits("macos")["open_files"]


def test_a_label_no_shell_here_prints_keeps_its_own_words() -> None:
    """Test an unknown resource is neither dropped nor guessed at."""
    parsed = _parse_ulimit(
        "@SOFT@\nquantum flux (jiffies)   42\n@HARD@\n", "test: "
    )[0]

    assert parsed == {
        "quantum_flux": {"soft": 42, "hard": None, "unit": "jiffies"}
    }


def test_two_labels_for_one_name_do_not_overwrite_each_other() -> None:
    """Test the second keeps its own words rather than the first's."""
    parsed = _parse_ulimit(
        "@SOFT@\nopen files   1024\nnofiles   99\n@HARD@\n", "test: "
    )[0]

    assert parsed["open_files"]["soft"] == 1024
    assert parsed["nofiles"]["soft"] == 99


def test_a_soft_only_answer_leaves_the_hard_ceiling_null() -> None:
    """Test a shell that named one set has not named the other."""
    parsed = _parse_ulimit("@SOFT@\ncpu time (seconds) 60\n", "test: ")[0]

    assert parsed["cpu_time"] == {"soft": 60, "hard": None, "unit": "seconds"}


def test_a_shell_with_no_ulimit_answers_nothing() -> None:
    """Test output the probe never reached parses to nothing."""
    assert _parse_ulimit("", "test: ") == (None, None)
    assert _parse_ulimit("sh: ulimit: not found\n", "test: ") == (None, None)


def test_the_marker_alone_is_not_a_set_of_limits() -> None:
    """Test a probe that ran and named nothing publishes nothing."""
    assert _parse_ulimit("@SOFT@\n@HARD@\n", "test: ") == (None, None)


@pytest.mark.parametrize(
    "printed,expected",
    [
        ("0022\n", "0022"),
        ("022\n", "0022"),  # zsh prints three digits
        ("0", "0000"),
        ("0077", "0077"),
        ("  0022  ", "0022"),
    ],
)
def test_a_mask_reads_as_the_octal_string_a_mode_is(
    printed: str, expected: str
) -> None:
    """Test every shell's mask arrives in one four-character form."""
    assert _parse_umask(printed, "test: ") == (expected, None)


@pytest.mark.parametrize("printed", ["", "   ", "u=rwx,g=rx,o=rx", "nope"])
def test_a_mask_that_is_not_octal_is_not_a_mask(printed: str) -> None:
    """Test a symbolic or absent answer is nothing, and not an error."""
    assert _parse_umask(printed, "test: ") == (None, None)


def test_the_probe_names_the_builtin_it_asks() -> None:
    """Test the request names ulimit rather than the shell reading it.

    The probe is a script, so argv names sh and sh is not what was
    asked.  A builtin is a command a fact may name like any other, so
    the request declares the one it asked.
    """
    requests = {
        request["type"]: request for request in get_limits_command_requests()
    }

    assert set(requests) == {"ulimit", "effective_uid"}

    script = requests["ulimit"]["command"]
    assert script[:2] == ("sh", "-c")
    assert "ulimit -aS" in script[2]
    assert "ulimit -aH" in script[2]
    assert requests["ulimit"]["evidence"] == ["ulimit"]


def test_the_uid_rides_with_the_limits() -> None:
    """Test who answered is asked for beside what they are limited to.

    A limit is a property of one session, and the answer says nothing
    without the identity it applies to, so the probe that names the
    identity travels with it.
    """
    requests = {
        request["type"]: request for request in get_limits_command_requests()
    }

    assert requests["effective_uid"]["command"] == ("id", "-u")


def test_the_spec_names_the_limits_probe_alone() -> None:
    """Test the mask is not asked for here.

    A umask is a product of the rc files a shell read and belongs to
    the shell and home that produced it, which is where the shell
    probes file it.  Asking twice would put two answers to one
    question in two namespaces.
    """
    assert set(LIMITS_COMMAND_SPEC) == {"posix"}
    assert set(LIMITS_COMMAND_SPEC["posix"]) == {"ulimit"}


def test_the_processor_answers_with_the_limits_alone() -> None:
    """Test the mask does not come back from the limits probe."""
    results = [
        {**request, "rc": 0, "stdout": corpus("ulimit_macos.txt")}
        for request in get_limits_command_requests()
        if request["type"] == "ulimit"
    ]

    fields, errors = process_limits_command_results(results)

    assert errors == []
    assert set(fields) == {"limits"}
    assert fields["limits"]["processes"]["soft"] == 10666


def test_a_probe_that_answered_nothing_files_no_field() -> None:
    """Test a shell that would not say leaves the fields out."""
    results = [
        {**request, "rc": 127, "stdout": "", "stderr": "not found"}
        for request in get_limits_command_requests()
    ]

    assert process_limits_command_results(results) == ({}, [])
    assert process_limits_command_results([]) == ({}, [])
