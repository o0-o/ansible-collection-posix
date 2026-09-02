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

"""Unit tests for sysctl_utils module.

Four corpora, two of them live captures and two constructed.

``sysctl_linux_casa.txt`` is an excerpt of a real ``sysctl -a`` off an
Arch host running procps - 5723 lines, cut to the 42 that carry every
form the listing takes, verbatim.  ``sysctl_macos.txt`` is the same
thing off a live macOS host.

``sysctl_freebsd.txt`` and ``sysctl_openbsd.txt`` are written by hand
from the formats those implementations document, because no host of
either was in reach.  Both carry the multiline ``kern.version`` those
kernels really hold, which is the form the parser is here for.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils.sysctl_utils import (
    SYSCTL_MISSING_RCS,
    _parse_sysctl,
    get_sysctl_assignment_requests,
    get_sysctl_key_requests,
    get_sysctl_listing_requests,
    process_sysctl_command_results,
)

FILES = Path(__file__).parent / "files"

# Which corpora came off a running host and which were written from
# the documented format, because a test that cannot say is a test
# nobody can weigh
LIVE = ("linux_casa", "macos")
CONSTRUCTED = ("freebsd", "openbsd")


def corpus(name: str) -> str:
    """Read one listing corpus.

    :param str name: The corpus suffix
    :returns str: The file's contents
    """
    return (FILES / f"sysctl_{name}.txt").read_text()


def parsed(name: str) -> dict:
    """Parse one listing corpus.

    :param str name: The corpus suffix
    :returns dict: The values keyed by key
    """
    values, errors = _parse_sysctl(0, corpus(name), "test: ")

    assert errors is None
    return values


@pytest.mark.parametrize("name", LIVE + CONSTRUCTED)
def test_every_implementation_s_separator_is_read(name: str) -> None:
    """Test all three listing forms reach the same shape.

    Linux procps prints ``key = value``, FreeBSD and macOS print
    ``key: value``, and OpenBSD prints ``key=value``.
    """
    values = parsed(name)

    assert len(values) > 10
    assert all(isinstance(key, str) for key in values)
    assert all(isinstance(value, str) for value in values.values())
    # No key carries a separator or the whitespace around one
    assert all(set(key).isdisjoint({" ", "\t", "=", ":"}) for key in values)


def test_a_value_carrying_the_separator_stays_whole() -> None:
    """Test a value with ``: `` in it is not cut at its own text.

    macOS answers kern.version with a string that has a colon in the
    middle of it, so a parser splitting on the first separator would
    put half the value in the key.
    """
    version = parsed("macos")["kern.version"]

    assert version.startswith("Darwin Kernel Version 25.5.0: Tue Jun")
    assert "kern.version" not in version


def test_a_bsd_multiline_value_joins_its_continuations() -> None:
    """Test an indented line continues the value before it.

    The BSDs print the first line of kern.version after the separator
    and the build path as a line of its own, and both are one string
    the kernel holds.
    """
    for name, opens in (
        ("freebsd", "FreeBSD 14.0-RELEASE"),
        ("openbsd", "OpenBSD 7.4 (GENERIC.MP)"),
    ):
        version = parsed(name)["kern.version"]
        lines = version.splitlines()

        assert len(lines) == 2
        assert lines[0].startswith(opens)
        assert lines[1].lstrip().startswith(("root@", "deraadt@"))


def test_a_linux_multiline_value_joins_its_repeated_keys() -> None:
    """Test a key printed once per line is one value, not the last one.

    procps spells a multiline value by printing the key again on every
    line, which both ``sysctl -a`` and a single-key query do, so a
    parser that let the last line win would answer with a fragment.
    """
    values = parsed("linux_casa")

    assert values["kernel.core_modes"] == "file\npipe\nsocket"

    # The corpus prints the key on 24 lines and the last of them is
    # empty, so the joined value ends in a newline and splitlines reads
    # that one as a terminator rather than as a line of its own
    info = values["dev.cdrom.info"].splitlines()

    assert corpus("linux_casa").count("dev.cdrom.info = ") == 24
    assert len(info) == 23
    assert info[0].startswith("CD-ROM information, Id: cdrom.c")
    assert "drive name:\t\tsr1\tsr0" in info


def test_a_value_that_looks_like_a_key_is_not_one() -> None:
    """Test the text of a value cannot open a new key.

    dev.cdrom.info prints lines reading "drive name:" and "Can read
    DVD:", which is the separator a BSD listing uses, inside a value.
    """
    values = parsed("linux_casa")

    assert "drive name" not in values
    assert "Can read DVD" not in values


def test_an_empty_value_is_an_empty_string() -> None:
    """Test a key the host printed nothing after keeps its key.

    An empty value is a value: the host was asked, answered, and what
    it answered was nothing.
    """
    assert parsed("linux_casa")["kernel.domainname"] == "(none)"
    assert parsed("macos")["kern.nisdomainname"] == ""
    assert parsed("freebsd")["kern.geom.confxml"] == ""


def test_a_slash_bearing_key_is_one_key() -> None:
    """Test an interface name with a slash in it does not split.

    A VLAN or bridge puts its own name in the key, and Linux lets that
    name carry a slash.
    """
    values = parsed("linux_casa")

    assert values["net.ipv4.conf.enp5s0/1.accept_local"] == "0"


def test_a_tab_separated_value_is_one_string() -> None:
    """Test a tuple the kernel prints with tabs is not split.

    What the fields of fs.dentry-state mean is the kernel's business,
    so the value is the string it printed.
    """
    assert "\t" in parsed("linux_casa")["fs.dentry-state"]


def test_output_naming_no_key_at_all_is_an_error() -> None:
    """Test genuinely unparseable output is not read as a value.

    A continuation continues something. Output whose first line opens
    no key is not a listing, and that is the one thing here that is a
    fault rather than an answer.
    """
    values, errors = _parse_sysctl(0, "command not found\n", "test: ")

    assert values is None
    assert errors is not None
    assert "naming no key" in str(errors[0])


def test_a_host_that_printed_nothing_answers_nothing() -> None:
    """Test an empty answer is None rather than an error.

    A refused key prints nothing, and a key that is not there is not a
    parser fault.
    """
    for rc in (0,) + SYSCTL_MISSING_RCS:
        assert _parse_sysctl(rc, "", "test: ") == (None, None)


def test_the_listing_asks_for_everything_in_one_command() -> None:
    """Test the default is one sysctl and not one per key."""
    requests = get_sysctl_listing_requests()

    assert len(requests) == 1
    assert requests[0]["command"] == ("sysctl", "-a")
    assert requests[0]["type"] == "sysctl_listing"


def test_a_named_key_is_asked_on_its_own() -> None:
    """Test one key per invocation, so a refusal has an owner.

    A host asked about five keys and refusing one says so once for the
    whole command, and which of the five it meant is then a guess.
    """
    requests = get_sysctl_key_requests(["vm.swappiness", "kernel.sysrq"])

    assert [request["command"] for request in requests] == [
        ("sysctl", "vm.swappiness"),
        ("sysctl", "kernel.sysrq"),
    ]


def test_an_assignment_is_written_plainly() -> None:
    """Test the set is ``sysctl key=value`` and never ``-w``.

    ``-w`` is the procps and FreeBSD spelling of it, and OpenBSD has no
    such flag, so the plain assignment is the portable one.
    """
    requests = get_sysctl_assignment_requests(
        {"vm.swappiness": "10", "kernel.sysrq": "0"}
    )

    assert [request["command"] for request in requests] == [
        ("sysctl", "kernel.sysrq=0"),
        ("sysctl", "vm.swappiness=10"),
    ]
    assert all("-w" not in request["command"] for request in requests)


def test_a_key_the_host_refused_is_null_and_not_absent() -> None:
    """Test a named key always gets an answer.

    The caller named it, so the answer is about that key, and null is
    this collection's word for asked about and not there.
    """
    keys = ["kernel.hostname", "kernel.nosuchkey"]
    results = []
    for request in get_sysctl_key_requests(keys):
        asked = request["command"][1]
        answered = asked == "kernel.hostname"
        results.append(
            {
                **request,
                "rc": 0 if answered else 1,
                "stdout": (
                    "kernel.hostname = casa-hank\n" if answered else ""
                ),
                "stderr": (
                    ""
                    if answered
                    else "sysctl: cannot stat /proc/sys/kernel/nosuchkey"
                ),
            }
        )

    values, errors = process_sysctl_command_results(results, keys)

    assert errors == []
    assert values == {
        "kernel.hostname": "casa-hank",
        "kernel.nosuchkey": None,
    }


def test_a_key_nobody_asked_about_is_not_answered() -> None:
    """Test the store holds what was asked and nothing else."""
    values, errors = process_sysctl_command_results([], [])

    assert values == {}
    assert errors == []


def test_a_listing_that_exited_non_zero_still_answers() -> None:
    """Test what the host printed is read whatever the status.

    ``sysctl -a`` exits non-zero on a host holding keys it will not
    read, having printed every key it would, which is what a real
    Linux host does.
    """
    text = corpus("linux_casa")
    results = [
        {
            **request,
            "rc": 1,
            "stdout": text,
            "stderr": "sysctl: permission denied on key ...",
        }
        for request in get_sysctl_listing_requests()
    ]

    values, errors = process_sysctl_command_results(results)

    assert errors == []
    assert values["kernel.ostype"] == "Linux"
