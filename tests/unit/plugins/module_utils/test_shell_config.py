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

"""Unit tests for the shell-context probe in shells_utils.

Every fixture here is the output of a login shell that actually ran.
That is the point of the probe rather than an accident of testing it:
a shell's configuration is code, and what the code does is not
readable off the files it lives in.  The captures show it - macOS's
``/bin/sh`` rewrites C(PATH) out of ``path_helper`` before it hands
you a prompt, and Debian's rewrites C(LANG) - so a fixture written
from what was handed in would be a fixture of the wrong thing.

Each was taken from a controlled starting environment, so the file is
short enough to read and carries no host's private variables.  What
the shell did to that environment is the shell's own doing and is
verbatim.
"""

from __future__ import annotations

import os

from typing import Any, Optional

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (
    SHELL_COMMAND_SPEC,
    SHELL_PROBE_SCRIPT,
)
from ansible_collections.o0_o.core.plugins.module_utils.evidence_utils import (  # noqa: E501
    name_origins,
)
from ansible_collections.o0_o.posix.plugins.module_utils.shells_utils import (
    SHELL_DEFAULT,
    SHELL_RCS,
    SHELL_SYSTEM_HOME,
    SHELL_ENV_VARS,
    _parse_shell_config,
    compose_shells,
    get_shell_command_requests,
    get_shell_login_requests,
    name_shell_binaries,
    process_shell_command_results,
)

FILES = os.path.join(os.path.dirname(__file__), "files")

# The shells whose login run was captured
SHELLS = (
    "linux_glibc",
    "linux_musl",
    "macos",
    "macos_ksh",
    "macos_zsh",
)

# The environment every capture was started from, so that what a
# shell changed can be told from what it inherited
HANDED_IN = {
    "PATH": "/usr/bin:/bin",
    "LANG": "en_US.UTF-8",
    "TERM": "xterm",
    "EDITOR": "vi",
}

# What each login shell changed about it, which is the whole reason
# the fact is an observation rather than a read of the files
CHANGED = {
    "linux_glibc": "LANG",
    "linux_musl": "PATH",
    "macos": "PATH",
    "macos_ksh": "PATH",
    "macos_zsh": "PATH",
}

# The shells whose host has no locale utility to ask
NO_LOCALE = ("linux_musl",)


def corpus(name: str) -> str:
    """Read a captured fixture verbatim.

    :param str name: File name under ``files/``
    :returns str: The file's contents
    """
    with open(os.path.join(FILES, name), encoding="utf-8") as handle:
        return handle.read()


def config(shell: str) -> Optional[dict[str, Any]]:
    """Parse one captured shell's probe output.

    :param str shell: The captured shell's name
    :returns Optional[dict[str, Any]]: What the combination produced
    """
    parsed, errors = _parse_shell_config(
        0, corpus(f"shell_config_{shell}.txt"), "test: "
    )
    assert errors is None
    return parsed


@pytest.mark.parametrize("shell", SHELLS)
def test_a_login_run_answers_a_mask_and_an_environment(shell: str) -> None:
    """Test every capture reaches the same three-field shape."""
    parsed = config(shell)

    assert parsed["umask"] == "0022"
    assert parsed["env"]["PATH"]
    # The placement the filer reads and removes travels beside them
    assert set(parsed) <= {"env", "umask", "locale", "_filing"}


@pytest.mark.parametrize("shell", SHELLS)
def test_every_watched_variable_is_answered_for(shell: str) -> None:
    """Test a row says what it was asked, not only what it found.

    ``env`` prints the whole exported environment, so for every name
    on the list the answer is known - a value, or a confirmed absence.
    The row says which, the way the path store says null for a path
    asked about and not there.
    """
    environment = config(shell)["env"]

    assert set(environment) == set(SHELL_ENV_VARS)
    assert all(
        value is None or isinstance(value, str)
        for value in environment.values()
    )


@pytest.mark.parametrize("shell", SHELLS)
def test_a_variable_the_shell_did_not_export_is_null(shell: str) -> None:
    """Test IFS reads null on a host where nothing is wrong with it.

    IFS is watched for the opposite reason to the rest: a value is the
    finding. Null is the healthy answer and says the question was put,
    which an absent key could not.
    """
    assert config(shell)["env"]["IFS"] is None


def test_a_row_that_answered_nothing_claims_nothing() -> None:
    """Test an empty block is not every variable confirmed unset.

    A login shell always exports something, so a block that printed
    nothing is a probe that did not answer - and a row of nulls would
    claim seven questions were put that never were.
    """
    parsed, errors = _parse_shell_config(
        0, "@UMASK@\n0022\n@ENV@\n@LOCALE@\n@END@\n", "test: "
    )

    assert errors is None
    assert "env" not in parsed
    assert parsed["umask"] == "0022"


@pytest.mark.parametrize("shell", SHELLS)
def test_the_login_files_ran_and_the_capture_shows_it(shell: str) -> None:
    """Test the answer is what the shell made, not what it was given.

    A shell that changed nothing would make the probe pointless and
    a read of the dot files sufficient. Every one of them changed
    something.
    """
    env = config(shell)["env"]
    variable = CHANGED[shell]

    assert env[variable] != HANDED_IN[variable]
    assert env[variable]


@pytest.mark.parametrize("shell", SHELLS)
def test_only_what_describes_the_shell_is_kept(shell: str) -> None:
    """Test the observation is not a copy of the whole environment.

    A shell's environment is a place secrets live, and observing one
    is not a reason to file it. Narrower than that: the fact is about
    a shell, so the identity variables a login environment carries
    say which user happened to run the probe rather than anything
    about the shell, and they are left out too.
    """
    env = config(shell)["env"]

    assert "NOT_A_POSIX_VARIABLE" not in env
    assert "SHLVL" not in env
    assert "_" not in env

    # Not an identity, however POSIX the name is
    for identity in ("HOME", "LOGNAME", "MAIL", "PWD", "USER"):
        assert identity not in env

    # The home the row was run out of is the key it is filed under,
    # and the shell is the entry it is filed in, so neither is a field
    assert "SHELL" not in env

    # What it does keep describes the shell: where it will look, what
    # locale it set, what terminal the session carries
    assert env["PATH"]
    assert set(env) <= set(SHELL_ENV_VARS)


@pytest.mark.parametrize("shell", SHELLS)
def test_a_locale_is_read_where_the_host_has_one_to_ask(
    shell: str,
) -> None:
    """Test a host with no locale utility has no locale field.

    A field the shell would not answer is left out rather than
    nulled: a configuration with no locale in it is a different claim
    from a locale that is unset.
    """
    parsed = config(shell)

    if shell in NO_LOCALE:
        assert "locale" not in parsed
    else:
        assert parsed["locale"]["language"]
        assert "all" in parsed["locale"]


def test_a_three_digit_mask_is_the_same_mask() -> None:
    """Test zsh's shorter mask reads as the mode every other one is."""
    assert config("macos_zsh")["umask"] == config("macos")["umask"]


def test_what_a_dot_file_printed_before_the_probe_is_discarded() -> None:
    """Test the answer starts at the marker, not at the first byte.

    A login shell may print anything it likes on the way in, and a
    dot file that echoes is still a dot file that ran.
    """
    noisy = "Welcome to the host!\nMOTD line two\n" + corpus(
        "shell_config_macos.txt"
    )

    assert _parse_shell_config(0, noisy, "test: ")[0] == config("macos")


def test_a_value_with_a_newline_in_it_stays_one_value() -> None:
    """Test a line that cannot start a variable continues the last."""
    parsed = _parse_shell_config(
        0,
        "@UMASK@\n0022\n@ENV@\nPATH=first line\nsecond line\n"
        "TERM=vt100\n@LOCALE@\n@END@\n",
        "test: ",
    )[0]

    assert parsed["env"]["PATH"] == "first line\nsecond line"
    assert parsed["env"]["TERM"] == "vt100"


@pytest.mark.parametrize("rc", [126, 127])
def test_a_shell_that_did_not_run_answers_nothing(rc: int) -> None:
    """Test a missing or unrunnable shell files no row at all."""
    assert _parse_shell_config(rc, "", "test: ") == (None, None)
    assert rc in SHELL_RCS


def test_output_without_the_marker_is_not_an_answer() -> None:
    """Test a probe whose script never started files no row."""
    assert _parse_shell_config(0, "", "test: ") == (None, None)
    assert _parse_shell_config(0, "some other output\n", "test: ") == (
        None,
        None,
    )


def test_a_probe_that_answered_only_junk_files_no_row() -> None:
    """Test a run that named none of the three fields is not a row."""
    assert _parse_shell_config(
        0, "@UMASK@\n@ENV@\n@LOCALE@\n@END@\n", "test: "
    ) == (None, None)


def test_the_probe_runs_the_shell_out_of_the_home_it_names() -> None:
    """Test the invocation is argv-clean and reads the login files."""
    requests = get_shell_command_requests([("/bin/zsh", "/home/o0-o")])

    assert len(requests) == 1
    command = requests[0]["command"]

    assert command[:5] == (
        "env",
        "HOME=/home/o0-o",
        "/bin/zsh",
        "-l",
        "-c",
    )
    assert requests[0]["type"] == "shell_config"
    assert requests[0]["non_error_codes"] == SHELL_RCS
    assert requests[0]["args"] == {"shell": "/bin/zsh", "home": "/home/o0-o"}


def test_a_home_with_a_space_in_it_reaches_the_shell_whole() -> None:
    """Test env(1) takes the assignment as an argument, not as syntax."""
    requests = get_shell_command_requests([("/bin/sh", "/Users/A Person")])

    assert requests[0]["command"][1] == "HOME=/Users/A Person"


def test_nothing_is_probed_that_was_not_asked_for() -> None:
    """Test the builder enumerates no shells of its own."""
    assert get_shell_command_requests([]) == []
    assert len(get_shell_command_requests([("/bin/sh", "/dev/null")])) == 1


def test_the_spec_names_the_two_ways_a_shell_is_asked() -> None:
    """Test the spec holds the two login runs and nothing else.

    One names the shell and the home; the other names a user and lets
    their passwd entry decide both, which is what a login su does.
    """
    assert set(SHELL_COMMAND_SPEC) == {"posix"}
    assert set(SHELL_COMMAND_SPEC["posix"]) == {
        "shell_config",
        "shell_login",
    }


def test_the_results_are_keyed_by_the_pair_that_decided_them() -> None:
    """Test a batch reads back as shell and then home."""
    pairs = [("/bin/sh", SHELL_SYSTEM_HOME), ("/bin/zsh", "/home/o0-o")]
    captures = {"/bin/sh": "macos", "/bin/zsh": "macos_zsh"}

    results = [
        {
            **request,
            "rc": 0,
            "stdout": corpus(
                f"shell_config_{captures[request['args']['shell']]}.txt"
            ),
        }
        for request in get_shell_command_requests(pairs)
    ]

    observed, consulted = process_shell_command_results(results)

    assert set(observed) == {"/bin/sh", "/bin/zsh"}
    assert set(observed["/bin/sh"]) == {SHELL_SYSTEM_HOME}
    assert set(observed["/bin/zsh"]) == {"/home/o0-o"}
    assert observed["/bin/zsh"]["/home/o0-o"]["umask"] == "0022"
    # Each shell's record is what was asked of it, not of the batch
    assert consulted["/bin/sh"]["commands"] == [
        "alias",
        "env",
        "locale",
        "sh",
        "umask",
    ]
    assert "zsh" in consulted["/bin/zsh"]["commands"]
    assert "sh" not in consulted["/bin/zsh"]["commands"]


def test_a_pair_that_answered_nothing_is_not_a_row() -> None:
    """Test a shell that did not run leaves the store unmentioned."""
    results = [
        {**request, "rc": 127, "stdout": "", "stderr": "not found"}
        for request in get_shell_command_requests(
            [("/bin/nosuchshell", SHELL_SYSTEM_HOME)]
        )
    ]

    assert process_shell_command_results(results) == ({}, {})
    assert process_shell_command_results([]) == ({}, {})


def test_the_named_shells_are_the_keys_and_the_idiom_survives() -> None:
    """Test user.shell in o0_shells reads as it always did."""
    shells = compose_shells(["/bin/sh", "/bin/zsh", "/bin/bash"])

    assert "/bin/zsh" in shells
    assert "/bin/nosuchshell" not in shells
    assert shells["/bin/zsh"] == {}


def test_an_observed_shell_the_host_did_not_name_is_a_key_too() -> None:
    """Test the host answered for it, so the fact carries it."""
    shells = compose_shells(
        ["/bin/sh"],
        {"/usr/local/bin/fish": {"/home/o0-o": {"umask": "0022"}}},
    )

    assert set(shells) == {"/bin/sh", "/usr/local/bin/fish"}
    assert shells["/bin/sh"] == {}
    assert shells["/usr/local/bin/fish"]["homes"]["/home/o0-o"] == {
        "umask": "0022"
    }


def test_a_shell_named_and_observed_carries_its_rows() -> None:
    """Test the two halves meet under one key."""
    shells = compose_shells(
        ["/bin/sh", "/bin/zsh"],
        {
            "/bin/sh": {
                SHELL_SYSTEM_HOME: {"umask": "0022"},
                "/home/o0-o": {"umask": "0077"},
            }
        },
    )

    assert set(shells) == {"/bin/sh", "/bin/zsh"}
    # Homes are a mapping of their own, so a home path is never a key
    # beside a field of the shell
    assert list(shells["/bin/sh"]) == ["homes"]
    assert list(shells["/bin/sh"]["homes"]) == ["/dev/null", "/home/o0-o"]
    assert shells["/bin/sh"]["homes"]["/home/o0-o"]["umask"] == "0077"
    assert shells["/bin/zsh"] == {}


def test_one_record_per_shell_names_everything_asked_of_it() -> None:
    """Test the shell carries the provenance, not each home.

    A shell observed out of two homes was asked the same way twice
    about one shell, and a shell whose builtins were enumerated was
    asked a second way about the same shell, so the record is one
    union at the shell rather than a copy under each home.
    """
    shells = compose_shells(
        ["/bin/sh", "/bin/zsh"],
        {
            "/bin/sh": {
                SHELL_SYSTEM_HOME: {"umask": "0022"},
                "/home/o0-o": {"umask": "0077"},
            }
        },
        {"/bin/sh": {"commands": ["env", "sh"]}},
        {"/bin/sh": ["cd"]},
        {"commands": ["command"]},
    )

    assert shells["/bin/sh"]["evidence"] == {
        "commands": ["command", "env", "sh"]
    }
    for home in ("/dev/null", "/home/o0-o"):
        assert "evidence" not in shells["/bin/sh"]["homes"][home]

    assert shells["/bin/zsh"] == {}


def test_a_shell_composed_without_a_probe_named_carries_none() -> None:
    """Test a caller that names nothing gets no evidence rather than a
    record claiming an origin it was never given."""
    shells = compose_shells(
        None, {"/bin/sh": {SHELL_SYSTEM_HOME: {"umask": "0022"}}}
    )

    assert shells["/bin/sh"] == {"homes": {"/dev/null": {"umask": "0022"}}}


def test_a_host_that_named_no_shells_and_ran_none_composes_nothing() -> None:
    """Test an empty answer is empty rather than invented."""
    assert compose_shells() == {}
    assert compose_shells(None, {}) == {}
    assert compose_shells([]) == {}


def test_the_canonical_home_and_shell_are_what_they_are_documented_as(
) -> None:
    """Test the two constants the docs name by value."""
    assert SHELL_SYSTEM_HOME == "/dev/null"
    assert SHELL_DEFAULT == "/bin/sh"


# What each of these captures had in the home it was run out of. The
# shells were run out of a home holding a dot file that defines them,
# because an alias is what a rc file makes and there is no other way
# to see one
ALIAS_SHELLS = ("macos_aliases", "macos_bash_aliases", "macos_zsh_aliases")
DEFINED_ALIASES = {"ll": "ls -l", "gs": "git status"}


@pytest.mark.parametrize("shell", ALIAS_SHELLS)
def test_an_alias_belongs_to_the_pair_that_made_it(shell: str) -> None:
    """Test the aliases a login shell had land in the row's config.

    An alias comes out of a rc file, so it is a fact about the shell
    and the home together, and it rides beside the environment, the
    mask and the locale that same probe answered with.
    """
    parsed = config(shell)

    assert parsed["aliases"]["ll"] == "ls -l"
    assert parsed["aliases"]["gs"] == "git status"


def test_both_spellings_of_an_alias_listing_are_read() -> None:
    """Test the two forms a real shell prints both parse.

    What ``alias`` prints is unspecified beyond being re-inputtable.
    bash prints ``alias ll='ls -l'`` and macOS's /bin/sh, which is the
    same bash in POSIX mode, prints ``ll='ls -l'``.
    """
    posix_mode = config("macos_aliases")["aliases"]
    bash_mode = config("macos_bash_aliases")["aliases"]

    assert posix_mode == DEFINED_ALIASES
    assert bash_mode == DEFINED_ALIASES


def test_a_shell_s_own_aliases_are_kept_with_the_home_s() -> None:
    """Test what the shell defines for itself is an alias too.

    zsh ships two of its own, one of them named with a hyphen and
    valued without quotes, which is a name and a value the parser has
    to take as it finds them.
    """
    aliases = config("macos_zsh_aliases")["aliases"]

    assert aliases["run-help"] == "man"
    assert aliases["which-command"] == "whence"
    assert aliases["ll"] == "ls -l"


@pytest.mark.parametrize("shell", SHELLS)
def test_a_capture_without_the_alias_section_still_parses(
    shell: str,
) -> None:
    """Test a probe that answered before the alias marker existed.

    These captures predate the alias section, so they end at the end
    marker with no alias block at all: the locale is still read to its
    own end and no aliases are claimed, which is what a shell that
    would not answer for them means.
    """
    parsed = config(shell)

    assert "aliases" not in parsed
    if shell not in NO_LOCALE:
        assert "@END@" not in str(parsed["locale"])


def test_a_shell_with_no_aliases_claims_none() -> None:
    """Test an empty alias listing is no aliases rather than an empty
    mapping, the way every other field the shell would not answer for
    is left out."""
    parsed, _errors = _parse_shell_config(
        0,
        "@UMASK@\n0022\n@ENV@\nPATH=/bin\n@LOCALE@\n@ALIAS@\n@END@\n",
        "",
    )

    assert "aliases" not in parsed


class TestBuiltinsSitOnTheShell:
    """Tests for where the commands a shell answers itself land."""

    def test_a_builtin_is_beside_the_rows_and_not_in_one(self) -> None:
        """Test builtins key the shell rather than a home.

        A builtin is intrinsic to the shell binary and no home changes
        which commands a shell is built out of, so it sits at the
        shell; every row's key is an absolute path and this one is a
        bare name, so the two never collide.
        """
        shells = compose_shells(
            ["/bin/sh"],
            {"/bin/sh": {"/dev/null": {"umask": "0022"}}},
            {"/bin/sh": {"commands": ["env"]}},
            {"/bin/sh": ["exec", "cd", "cd"]},
        )

        assert shells["/bin/sh"]["builtins"] == ["cd", "exec"]
        assert shells["/bin/sh"]["homes"]["/dev/null"] == {"umask": "0022"}
        assert "builtins" not in shells["/bin/sh"]["homes"]["/dev/null"]

    def test_a_shell_known_only_by_its_builtins_is_a_key(self) -> None:
        """Test a shell nothing else named still gets a key.

        The sweep ran its probes through it, which is the host
        answering for that shell as surely as naming it would be.
        """
        shells = compose_shells(builtins={"/bin/sh": ["command"]})

        assert shells == {"/bin/sh": {"builtins": ["command"]}}

    def test_a_shell_with_no_builtins_named_carries_none(self) -> None:
        """Test a composition handed no builtins claims none."""
        shells = compose_shells(["/bin/sh"])

        assert shells == {"/bin/sh": {}}


def test_a_row_names_who_composed_it_beside_what_ran() -> None:
    """Test origins reaches a row two levels down.

    A row is keyed by shell and then by home, and it is where the
    evidence sits because it is where a probe happened, so it is where
    origins sits too.
    """
    shells = compose_shells(
        ["/bin/sh"],
        {"/bin/sh": {"/dev/null": {"umask": "0022"}}},
        {"/bin/sh": {"commands": ["env"]}},
        {"/bin/sh": ["cd"]},
    )

    name_origins(shells, "o0_o.posix.facts")

    # The record sits at the shell now, so the producer is named there
    assert shells["/bin/sh"]["origins"] == ["o0_o.posix.facts"]
    assert "origins" not in shells["/bin/sh"]["homes"]["/dev/null"]
    # and a shell named but never run has no observation to attribute
    assert compose_shells(["/bin/zsh"])["/bin/zsh"] == {}


class TestShellBinaries:
    """Tests for the file a shell's name finally resolves to."""

    STORE = {
        "/bin/sh": {
            "type": "link",
            "resolution": ["/bin/sh", "/usr/bin/sh", "/usr/bin/bash"],
        },
        "/bin/rbash": {
            "type": "link",
            "resolution": ["/bin/rbash", "/usr/bin/bash"],
        },
        "/bin/zsh": {"type": "regular", "resolution": ["/bin/zsh"]},
        "/usr/bin/bash": {"type": "regular"},
    }

    def test_a_shell_points_at_the_end_of_its_chain(self) -> None:
        """Test the pointer is the chain's last step, not a new walk."""
        shells = name_shell_binaries(
            compose_shells(["/bin/sh", "/bin/rbash"]), self.STORE
        )

        assert shells["/bin/sh"]["binary"] == "/usr/bin/bash"
        assert shells["/bin/rbash"]["binary"] == "/usr/bin/bash"

    def test_two_names_for_one_file_stay_two_entries(self) -> None:
        """Test the keys are the names the host uses.

        Behavior follows the invoked name - bash as sh is in POSIX
        mode and as rbash is restricted - so two names for one file
        are two observations, and what they share is the file.
        """
        shells = name_shell_binaries(
            compose_shells(["/bin/sh", "/bin/rbash", "/usr/bin/bash"]),
            self.STORE,
        )

        assert set(shells) == {"/bin/sh", "/bin/rbash", "/usr/bin/bash"}
        assert (
            shells["/bin/sh"]["binary"]
            == shells["/bin/rbash"]["binary"]
            == shells["/usr/bin/bash"]["binary"]
        )

    def test_a_shell_that_is_only_itself_points_at_itself(self) -> None:
        """Test a described non-link resolves to itself.

        Which is what a path that is nothing but itself resolves to, so
        a consumer reads one field without an existence check.
        """
        shells = name_shell_binaries(
            compose_shells(["/bin/zsh", "/usr/bin/bash"]), self.STORE
        )

        assert shells["/bin/zsh"]["binary"] == "/bin/zsh"
        assert shells["/usr/bin/bash"]["binary"] == "/usr/bin/bash"

    def test_a_shell_nothing_described_gets_no_pointer(self) -> None:
        """Test a shell no read reached claims no resolution.

        Nothing walked it, and a self-pointer would assert an answer
        nobody checked.
        """
        shells = name_shell_binaries(
            compose_shells(["/bin/ksh"]), self.STORE
        )

        assert "binary" not in shells["/bin/ksh"]

    def test_a_store_with_nothing_in_it_points_at_nothing(self) -> None:
        """Test a gather that read no path names no binary."""
        shells = name_shell_binaries(compose_shells(["/bin/sh"]), None)

        assert shells["/bin/sh"] == {}

    def test_a_null_at_the_path_is_not_a_description(self) -> None:
        """Test a shell the store holds as absent gets no pointer."""
        shells = name_shell_binaries(
            compose_shells(["/bin/gone"]), {"/bin/gone": None}
        )

        assert "binary" not in shells["/bin/gone"]

    def test_a_name_the_store_keys_differently_still_finds_it(self) -> None:
        """Test the pointer is looked up the way the store keys a path."""
        shells = name_shell_binaries(
            compose_shells(["/bin//sh"]),
            {"/bin/sh": {"type": "regular"}},
        )

        assert shells["/bin//sh"]["binary"] == "/bin/sh"


class TestLoginProbeConstructions:
    """Tests for how a shell is asked out of a reset environment."""

    def test_a_login_probe_names_the_user_and_not_a_shell(self) -> None:
        """Test the probe is not told which shell to run.

        The user's passwd entry decides, which is the whole reason to
        ask this way, so the request names the user and the answer
        says which shell it turned out to be.
        """
        (request,) = get_shell_login_requests(["o0-o"])

        assert request["command"] == (
            "su",
            "-",
            "o0-o",
            "-c",
            SHELL_PROBE_SCRIPT,
        )
        assert request["type"] == "shell_login"

    def test_a_login_probe_names_su_and_the_questions(self) -> None:
        """Test no shell is named where none was asked for.

        su is a command the probe execs to get there, so it is named;
        the shell is named later, on the row the answer files.
        """
        (request,) = get_shell_login_requests(["root"])

        assert request["evidence"] == [
            "alias",
            "env",
            "locale",
            "su",
            "umask",
        ]

    def test_a_dropped_system_probe_wraps_the_named_shell(self) -> None:
        """Test the shell we name is still the shell that runs.

        The system layer names its shell and forces its home, and the
        login su only decides whose environment it runs in.
        """
        (request,) = get_shell_command_requests(
            [("/bin/sh", SHELL_SYSTEM_HOME)], dropper="root"
        )

        assert request["command"][:4] == ("su", "-", "root", "-c")
        assert request["command"][4].startswith("env HOME=/dev/null /bin/sh")
        assert "su" in request["evidence"]
        assert "sh" in request["evidence"]

    def test_an_undropped_probe_is_the_bare_one(self) -> None:
        """Test a run that cannot drop asks exactly as it always did."""
        (request,) = get_shell_command_requests(
            [("/bin/sh", SHELL_SYSTEM_HOME)]
        )

        assert request["command"][0] == "env"
        assert "su" not in request["evidence"]

    def test_a_login_answer_files_itself(self) -> None:
        """Test the probe is the evidence for its own placement.

        Nobody told this probe which shell or which home, so the row
        goes where its own login environment says it belongs.
        """
        (request,) = get_shell_login_requests(["o0-o"])
        results = [
            {
                **request,
                "rc": 0,
                "stdout": (
                    "@UMASK@\n0022\n@ENV@\n"
                    "SHELL=/bin/zsh\nHOME=/home/o0-o\nPATH=/usr/bin\n"
                    "@LOCALE@\n@ALIAS@\n@END@\n"
                ),
            }
        ]

        observed, consulted = process_shell_command_results(results)

        assert set(observed) == {"/bin/zsh"}
        assert set(observed["/bin/zsh"]) == {"/home/o0-o"}
        # Neither the shell nor the home is published inside the row:
        # each is the key it was filed under
        row = observed["/bin/zsh"]["/home/o0-o"]
        assert "SHELL" not in row["env"]
        assert "HOME" not in row["env"]
        assert "_filing" not in row
        # The shell that turned out to run is named on its record
        assert "zsh" in consulted["/bin/zsh"]["commands"]

    def test_a_login_answer_that_named_no_placement_files_nothing(
        self,
    ) -> None:
        """Test a probe whose environment named neither is not a row.

        Without a shell and a home there is no key to file it under,
        and a guessed key would claim an observation of something
        nobody observed.
        """
        (request,) = get_shell_login_requests(["o0-o"])
        results = [
            {
                **request,
                "rc": 0,
                "stdout": "@UMASK@\n0022\n@ENV@\nPATH=/usr/bin\n"
                "@LOCALE@\n@ALIAS@\n@END@\n",
            }
        ]

        assert process_shell_command_results(results) == ({}, {})
