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

"""Unit tests for getconf_utils module.

Every fixture here was captured off a running host rather than
written from a manpage, because the manpages are exactly what
disagree: no two ``getconf`` implementations know the same variables,
and each refuses the ones it does not know in its own dialect and with
its own exit status.  Only what each of them actually printed settles
which refusals the sweep has to survive.  The captures live beside
this file in ``files/`` - one verbatim transcript per platform,
holding every variable's exit status, stdout and stderr as the host
gave them.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import pytest

from ansible_collections.o0_o.core.plugins.module_utils import (
    process_all_command_results,
)

from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (
    GETCONF_COMMAND_SPEC,
)
from ansible_collections.o0_o.posix.plugins.module_utils.getconf_utils import (
    GETCONF_RCS,
    GETCONF_SYSCONF_VARIABLES,
    _parse_getconf,
    compose_getconf,
    get_getconf_command_requests,
    process_getconf_command_results,
)

FILES = os.path.join(os.path.dirname(__file__), "files")

# The platforms whose sweep was captured
PLATFORMS = ("linux_glibc", "linux_musl", "macos")

# What each platform refused, and the exit status it refused with.
# The three dialects are the reason the sweep reads more than one
# status as an answer: musl says 1, glibc says 2, macOS says 64.
REFUSED = {
    "linux_glibc": {
        "NPROCESSORS_CONF": 2,
        "NPROCESSORS_ONLN": 2,
        "_POSIX2_VERSION": 2,
    },
    "linux_musl": {
        "CS_PATH": 1,
        "HOST_NAME_MAX": 1,
        "NPROCESSORS_CONF": 1,
        "NPROCESSORS_ONLN": 1,
        "SYMLOOP_MAX": 1,
        "TTY_NAME_MAX": 1,
        "_POSIX2_VERSION": 1,
        "_XOPEN_VERSION": 1,
    },
    "macos": {"CS_PATH": 64},
}

# What each platform has and does not limit, which is a value rather
# than a refusal and keeps its key
UNDEFINED = {
    "linux_glibc": ("SYMLOOP_MAX", "TZNAME_MAX"),
    "linux_musl": ("ATEXIT_MAX", "EXPR_NEST_MAX", "LINE_MAX", "STREAM_MAX"),
    "macos": (),
}


def corpus(name: str) -> str:
    """Read a captured fixture verbatim.

    :param str name: File name under ``files/``
    :returns str: The file's contents
    """
    with open(os.path.join(FILES, name), encoding="utf-8") as handle:
        return handle.read()


def sweep(platform: str) -> dict[str, dict[str, Any]]:
    """Read one platform's capture into an answer per variable.

    :param str platform: The captured platform's name
    :returns dict[str, dict[str, Any]]: Each variable's rc, stdout and
        stderr, keyed by the variable asked for
    """
    found: dict[str, dict[str, Any]] = {}
    current: Optional[dict[str, Any]] = None
    where = "stdout"

    for line in corpus(f"getconf_sysconf_{platform}.txt").splitlines():
        if line.startswith("===CMD=== getconf "):
            variable = line[len("===CMD=== getconf ") :]
            current = {"stdout": [], "stderr": [], "rc": None}
            found[variable] = current
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
        variable: {
            "rc": answer["rc"],
            "stdout": "\n".join(answer["stdout"]),
            "stderr": "\n".join(answer["stderr"]),
        }
        for variable, answer in found.items()
    }


def completed(platform: str) -> list[dict[str, Any]]:
    """Replay one platform's capture as a batch's results.

    Each request the sweep would have sent is paired with what the
    captured host answered it, so the whole path from spec to fact
    runs over output a host actually printed.

    :param str platform: The captured platform's name
    :returns list[dict[str, Any]]: Command results for the processor
    """
    answers = sweep(platform)
    results = []

    for request in get_getconf_command_requests():
        variable = request["args"]["var"]
        answer = answers[variable]
        results.append({**request, **answer})

    return results


def test_the_capture_covers_every_variable_the_sweep_asks_for() -> None:
    """Test each capture answers exactly the swept variables."""
    for platform in PLATFORMS:
        assert set(sweep(platform)) == set(GETCONF_SYSCONF_VARIABLES)


@pytest.mark.parametrize("platform", PLATFORMS)
def test_every_refusal_is_a_status_the_sweep_allows(platform: str) -> None:
    """Test no captured refusal would be read as a command failure."""
    for variable, answer in sweep(platform).items():
        assert answer["rc"] in GETCONF_RCS, variable


@pytest.mark.parametrize("platform", PLATFORMS)
def test_a_refused_variable_is_none_and_never_an_error(
    platform: str,
) -> None:
    """Test a variable the host does not know parses to nothing."""
    answers = sweep(platform)

    for variable, rc in REFUSED[platform].items():
        answer = answers[variable]
        assert answer["rc"] == rc
        assert answer["stderr"] != ""

        parsed, errors = _parse_getconf(
            answer["rc"], answer["stdout"], "test: "
        )
        assert parsed is None
        assert errors is None


@pytest.mark.parametrize("platform", PLATFORMS)
def test_a_number_parses_as_an_integer(platform: str) -> None:
    """Test the numeric answers come back as ints, not strings."""
    answer = sweep(platform)["ARG_MAX"]
    parsed, errors = _parse_getconf(answer["rc"], answer["stdout"], "test: ")

    assert isinstance(parsed, int)
    assert parsed > 0
    assert errors is None


@pytest.mark.parametrize("platform", PLATFORMS)
def test_a_path_stays_a_string(platform: str) -> None:
    """Test the confstr answers are not coerced to numbers."""
    answer = sweep(platform)["PATH"]
    parsed, errors = _parse_getconf(answer["rc"], answer["stdout"], "test: ")

    assert isinstance(parsed, str)
    assert parsed.startswith("/")
    assert errors is None


def test_undefined_parses_to_none() -> None:
    """Test the word a host uses for no limit carries no value."""
    parsed, errors = _parse_getconf(0, "undefined\n", "test: ")

    assert parsed is None
    assert errors is None


@pytest.mark.parametrize("platform", PLATFORMS)
def test_undefined_keeps_its_key_and_a_refusal_does_not(
    platform: str,
) -> None:
    """Test the fact tells no limit from no such variable."""
    config = compose_getconf(
        process_all_command_results(completed(platform))["getconf_sysconf"]
    )

    for variable in UNDEFINED[platform]:
        assert variable in config
        assert config[variable] is None

    for variable in REFUSED[platform]:
        assert variable not in config


@pytest.mark.parametrize("platform", PLATFORMS)
def test_the_captured_sweep_composes_the_os_config_fact(
    platform: str,
) -> None:
    """Test a whole platform's capture reaches the fact intact."""
    facts, errors = process_getconf_command_results(completed(platform))

    assert errors == []
    config = facts["o0_os"]["config"]

    # Answered everywhere, and a count rather than a path
    for variable in ("ARG_MAX", "CHILD_MAX", "OPEN_MAX", "_POSIX_VERSION"):
        assert isinstance(config[variable], int)

    assert isinstance(config["PATH"], str)

    # Whichever spelling of the processor count the host answers to,
    # and never one it does not
    assert "_NPROCESSORS_ONLN" in config
    assert ("NPROCESSORS_ONLN" in config) == (platform == "macos")


def test_a_host_with_no_getconf_publishes_no_namespace() -> None:
    """Test a sweep that answered nothing leaves o0_os unpublished."""
    results = [
        {**request, "rc": 127, "stdout": "", "stderr": "getconf: not found"}
        for request in get_getconf_command_requests()
    ]

    facts, errors = process_getconf_command_results(results)

    assert facts == {}
    assert errors == []


def test_a_batch_without_the_sweep_publishes_no_namespace() -> None:
    """Test a batch the sweep did not ride leaves o0_os unpublished."""
    facts, errors = process_getconf_command_results([])

    assert facts == {}
    assert errors == []


def test_the_spec_sends_one_request_per_variable() -> None:
    """Test the sweep expands to a command for each variable asked."""
    requests = get_getconf_command_requests()

    assert len(requests) == len(GETCONF_SYSCONF_VARIABLES)
    assert [request["args"]["var"] for request in requests] == list(
        GETCONF_SYSCONF_VARIABLES
    )

    for request in requests:
        variable = request["args"]["var"]
        assert request["type"] == "getconf_sysconf"
        assert request["command"] == ("getconf", variable)
        assert request["non_error_codes"] == GETCONF_RCS


def test_the_spec_asks_only_for_the_variables_it_was_given() -> None:
    """Test a caller may narrow the sweep to what it needs."""
    requests = get_getconf_command_requests(("ARG_MAX", "PATH"))

    assert [request["command"] for request in requests] == [
        ("getconf", "ARG_MAX"),
        ("getconf", "PATH"),
    ]


def test_the_spec_names_one_command_type() -> None:
    """Test the sysconf sweep is the spec's only posix entry so far."""
    assert set(GETCONF_COMMAND_SPEC) == {"posix"}
    assert "getconf_sysconf" in GETCONF_COMMAND_SPEC["posix"]
