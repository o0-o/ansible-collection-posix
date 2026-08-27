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

"""Unit tests for the commands lookup plugin."""

from __future__ import annotations

from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from ansible.errors import AnsibleLookupError

from ansible_collections.o0_o.posix.plugins.lookup.commands import (
    LookupModule,
    canonicalize,
)

# What a producer files at a path a command resolved to. command -v
# names an executable it would run without reading the mode, and a
# producer that read the mode says so instead; either settles the bit
INFERRED = {"executable": True, "executable_evidence": "inferred"}
PROBED = {"executable": True, "executable_evidence": "probed"}

# A file the store read and found will not run
NOT_EXECUTABLE = {"executable": False, "executable_evidence": "probed"}

# A path the store has an observation of that never settles the
# executable bit. The mode is not read as one: the lookup answers off
# the key the producers write, not off what a mode implies
UNSETTLED = {"type": "regular", "mode": "0755", "uid": 0, "gid": 0}

# The search path the environment subset gathers for the connecting
# user, and the entry it nests under
GATHERED = "/usr/local/bin:/usr/bin:/bin"
USERS = {
    "1000": {
        "name": "o0-o",
        "uid": 1000,
        "environment": {"PATH": GATHERED},
    }
}

# Every invalid entry class, each one a directory no store can key
INVALID_ENTRIES = [
    ("bin", "is not an absolute path"),
    ("./bin", "is not an absolute path"),
    ("../bin", "is not an absolute path"),
    ("~", "is not an absolute path"),
    ("~/bin", "is not an absolute path"),
    ("", "is not an absolute path"),
    (1, "is not a string"),
    (None, "is not a string"),
    (["/bin"], "is not a string"),
]


class FakeTemplar:
    """Stand in for the templar a lookup reads variables through.

    ``lookup_var`` reads ``available_variables`` and ``run`` templates
    every term, so those two are the whole of the seam. Terms pass
    through untouched unless the test supplies a substitution.
    """

    def __init__(
        self,
        variables: dict[str, Any],
        substitutions: Optional[dict[str, Any]] = None,
    ) -> None:
        self.available_variables = variables
        self._substitutions = substitutions or {}

    def template(self, value: Any) -> Any:
        """Resolve a term the way the templar would."""
        if isinstance(value, str) and value in self._substitutions:
            return self._substitutions[value]
        return value


@pytest.fixture
def make_lookup():
    """Build a lookup reading a namespace the test supplies.

    The display is mocked so a warned-about search path entry can be
    read back rather than printed.

    :returns: A factory taking the namespace as keyword arguments
    """

    def _make(
        substitutions: Optional[dict[str, Any]] = None,
        **variables: Any,
    ) -> LookupModule:
        lookup = LookupModule(
            loader=None,
            templar=FakeTemplar(variables, substitutions),
        )
        lookup._display = MagicMock()
        return lookup

    return _make


@pytest.fixture
def gathered(make_lookup):
    """Build a lookup over a store the test supplies and the
    gathered PATH.

    :returns: A factory taking the o0_paths store
    """

    def _make(paths: dict[str, Any]) -> LookupModule:
        return make_lookup(o0_paths=paths, o0_users=USERS)

    return _make


# ---------------------------------------------------------------------
# The tri-state answer
# ---------------------------------------------------------------------


def test_a_resolved_name_answers_the_path_it_resolved_to(
    gathered,
) -> None:
    """Test that a resolution names the candidate that answered."""

    lookup = gathered({"/usr/local/bin/ls": None, "/usr/bin/ls": INFERRED})

    assert lookup.run(["ls"], None) == [
        {"command": "ls", "state": "resolved", "path": "/usr/bin/ls"}
    ]


def test_a_name_gathered_absent_everywhere_answers_missing(
    gathered,
) -> None:
    """Test that a confirmed absence carries a null path."""

    lookup = gathered(
        {
            "/usr/local/bin/doas": None,
            "/usr/bin/doas": None,
            "/bin/doas": None,
        }
    )

    assert lookup.run(["doas"], None) == [
        {"command": "doas", "state": "missing", "path": None}
    ]


def test_an_unknown_carries_no_path_key_at_all(gathered) -> None:
    """Test that an unknown answer has no path key to read."""

    lookup = gathered({})

    (answer,) = lookup.run(["rsync"], None)

    assert answer == {"command": "rsync", "state": "unknown"}
    assert "path" not in answer


def test_the_three_states_are_told_apart_by_the_path_key(
    gathered,
) -> None:
    """Test that one call answers each state in its own shape."""

    lookup = gathered(
        {
            "/usr/local/bin/ls": None,
            "/usr/bin/ls": INFERRED,
            "/usr/local/bin/doas": None,
            "/usr/bin/doas": None,
            "/bin/doas": None,
        }
    )

    assert lookup.run(["ls", "doas", "rsync"], None) == [
        {"command": "ls", "state": "resolved", "path": "/usr/bin/ls"},
        {"command": "doas", "state": "missing", "path": None},
        {"command": "rsync", "state": "unknown"},
    ]


def test_every_name_asked_for_is_answered_in_order(gathered) -> None:
    """Test that the answers line up with the terms one for one."""

    lookup = gathered({})

    answers = lookup.run(["a", "b", "c", "a"], None)

    assert [answer["command"] for answer in answers] == [
        "a",
        "b",
        "c",
        "a",
    ]


def test_a_term_is_templated_before_it_is_resolved(make_lookup) -> None:
    """Test that a term carrying an expression resolves through it."""

    lookup = make_lookup(
        substitutions={"{{ cmd }}": "ls"},
        o0_paths={"/usr/local/bin/ls": PROBED},
        o0_users=USERS,
    )

    assert lookup.run(["{{ cmd }}"], None) == [
        {
            "command": "ls",
            "state": "resolved",
            "path": "/usr/local/bin/ls",
        }
    ]


@pytest.mark.parametrize("entry", [INFERRED, PROBED])
def test_either_evidence_settles_the_executable_bit(
    gathered, entry: dict[str, Any]
) -> None:
    """Test that how the bit was learned does not change the
    answer."""

    lookup = gathered({"/usr/local/bin/ls": entry})

    assert lookup.run(["ls"], None) == [
        {
            "command": "ls",
            "state": "resolved",
            "path": "/usr/local/bin/ls",
        }
    ]


# ---------------------------------------------------------------------
# Search order
# ---------------------------------------------------------------------


def test_the_first_candidate_reached_wins(gathered) -> None:
    """Test that the search stops where the host's own would."""

    lookup = gathered(
        {
            "/usr/local/bin/ls": INFERRED,
            "/usr/bin/ls": INFERRED,
            "/bin/ls": INFERRED,
        }
    )

    assert lookup.run(["ls"], None)[0]["path"] == "/usr/local/bin/ls"


def test_a_null_in_an_earlier_directory_does_not_stop_the_search(
    gathered,
) -> None:
    """Test that a name absent early and present late resolves."""

    lookup = gathered(
        {
            "/usr/local/bin/ls": None,
            "/usr/bin/ls": None,
            "/bin/ls": INFERRED,
        }
    )

    assert lookup.run(["ls"], None) == [
        {"command": "ls", "state": "resolved", "path": "/bin/ls"}
    ]


def test_a_file_that_will_not_run_is_passed_over(gathered) -> None:
    """Test that a gathered non-executable is not a resolution."""

    lookup = gathered(
        {
            "/usr/local/bin/ls": None,
            "/usr/bin/ls": NOT_EXECUTABLE,
            "/bin/ls": INFERRED,
        }
    )

    assert lookup.run(["ls"], None) == [
        {"command": "ls", "state": "resolved", "path": "/bin/ls"}
    ]


def test_a_non_executable_at_every_candidate_is_missing(
    gathered,
) -> None:
    """Test that a file that will not run is an absence, not a
    find."""

    lookup = gathered(
        {
            "/usr/local/bin/ls": NOT_EXECUTABLE,
            "/usr/bin/ls": NOT_EXECUTABLE,
            "/bin/ls": NOT_EXECUTABLE,
        }
    )

    assert lookup.run(["ls"], None) == [
        {"command": "ls", "state": "missing", "path": None}
    ]


def test_a_resolution_behind_an_ungathered_candidate_is_unknown(
    gathered,
) -> None:
    """Test that a candidate that could have answered first wins by
    withholding an answer."""

    lookup = gathered({"/bin/ls": INFERRED})

    assert lookup.run(["ls"], None) == [{"command": "ls", "state": "unknown"}]


def test_a_candidate_with_an_unsettled_bit_is_ungathered(
    gathered,
) -> None:
    """Test that an observation saying nothing about the bit is not
    an answer, whatever the mode says."""

    lookup = gathered(
        {
            "/usr/local/bin/ls": UNSETTLED,
            "/usr/bin/ls": INFERRED,
            "/bin/ls": None,
        }
    )

    assert lookup.run(["ls"], None) == [{"command": "ls", "state": "unknown"}]


def test_an_unsettled_bit_behind_a_resolution_does_not_reach_it(
    gathered,
) -> None:
    """Test that the search stops before an unsettled candidate it
    would never have reached."""

    lookup = gathered(
        {
            "/usr/local/bin/ls": INFERRED,
            "/usr/bin/ls": UNSETTLED,
        }
    )

    assert lookup.run(["ls"], None) == [
        {
            "command": "ls",
            "state": "resolved",
            "path": "/usr/local/bin/ls",
        }
    ]


# ---------------------------------------------------------------------
# Missing is every candidate, gathered
# ---------------------------------------------------------------------


def test_missing_requires_every_candidate_gathered_as_null(
    gathered,
) -> None:
    """Test that a full sweep of nulls is what a confirmed absence
    takes."""

    lookup = gathered(
        {
            "/usr/local/bin/doas": None,
            "/usr/bin/doas": None,
            "/bin/doas": None,
        }
    )

    assert lookup.run(["doas"], None)[0]["state"] == "missing"


@pytest.mark.parametrize(
    "ungathered",
    ["/usr/local/bin/doas", "/usr/bin/doas", "/bin/doas"],
)
def test_one_ungathered_candidate_makes_it_unknown(
    gathered, ungathered: str
) -> None:
    """Test that a single gap anywhere in the search withholds the
    absence."""

    paths = {
        "/usr/local/bin/doas": None,
        "/usr/bin/doas": None,
        "/bin/doas": None,
    }
    del paths[ungathered]

    lookup = gathered(paths)

    assert lookup.run(["doas"], None) == [
        {"command": "doas", "state": "unknown"}
    ]


def test_a_search_path_with_no_entries_resolves_nothing(
    gathered,
) -> None:
    """Test that a path nothing can be found in is an absence."""

    lookup = gathered({})

    assert lookup.run(["ls"], None, path=[]) == [
        {"command": "ls", "state": "missing", "path": None}
    ]


# ---------------------------------------------------------------------
# Which search path is followed
# ---------------------------------------------------------------------


def test_the_gathered_path_is_followed_by_default(gathered) -> None:
    """Test that the environment subset's PATH is the default."""

    lookup = gathered(
        {"/usr/local/bin/ls": None, "/usr/bin/ls": None, "/bin/ls": None}
    )

    assert lookup.run(["ls"], None)[0]["state"] == "missing"


def test_a_supplied_path_string_splits_on_the_separator(
    gathered,
) -> None:
    """Test that a string path is read the way PATH is read."""

    lookup = gathered({"/opt/bin/ls": None, "/sbin/ls": INFERRED})

    assert lookup.run(["ls"], None, path="/opt/bin:/sbin") == [
        {"command": "ls", "state": "resolved", "path": "/sbin/ls"}
    ]


def test_a_supplied_path_list_is_already_its_entries(gathered) -> None:
    """Test that a list path is searched in the order given."""

    lookup = gathered({"/opt/bin/ls": None, "/sbin/ls": INFERRED})

    assert lookup.run(["ls"], None, path=["/opt/bin", "/sbin"]) == [
        {"command": "ls", "state": "resolved", "path": "/sbin/ls"}
    ]


def test_a_supplied_path_replaces_the_gathered_one(gathered) -> None:
    """Test that a gathered directory is not searched alongside a
    supplied path."""

    lookup = gathered({"/usr/bin/ls": INFERRED, "/opt/bin/ls": None})

    assert lookup.run(["ls"], None, path="/opt/bin") == [
        {"command": "ls", "state": "missing", "path": None}
    ]


def test_a_supplied_path_entry_is_keyed_canonically(gathered) -> None:
    """Test that a loosely written entry still keys the store."""

    lookup = gathered({"/usr/bin/ls": INFERRED})

    assert lookup.run(["ls"], None, path="/usr//bin/") == [
        {"command": "ls", "state": "resolved", "path": "/usr/bin/ls"}
    ]


def test_path_and_user_are_mutually_exclusive(gathered) -> None:
    """Test that a supplied path is nobody's environment."""

    lookup = gathered({})

    with pytest.raises(AnsibleLookupError, match="mutually exclusive"):
        lookup.run(["ls"], None, path="/bin", user="o0-o")


@pytest.mark.parametrize("user", ["o0-o", 1000])
def test_a_named_user_s_gathered_path_is_followed(
    make_lookup, user: Any
) -> None:
    """Test that a user names their own PATH, by name or by UID."""

    lookup = make_lookup(
        o0_paths={"/opt/pg/bin/psql": INFERRED},
        o0_users={
            "0": {
                "name": "root",
                "uid": 0,
                "environment": {"PATH": "/sbin"},
            },
            "1000": {
                "name": "o0-o",
                "uid": 1000,
                "environment": {"PATH": "/opt/pg/bin"},
            },
        },
    )

    assert lookup.run(["psql"], None, user=user) == [
        {
            "command": "psql",
            "state": "resolved",
            "path": "/opt/pg/bin/psql",
        }
    ]


def test_several_gathered_paths_with_no_user_named_fail(
    make_lookup,
) -> None:
    """Test that an ambiguous environment names the users it found."""

    lookup = make_lookup(
        o0_paths={},
        o0_users={
            "0": {
                "name": "root",
                "uid": 0,
                "environment": {"PATH": "/sbin"},
            },
            "1000": {
                "name": "o0-o",
                "uid": 1000,
                "environment": {"PATH": "/bin"},
            },
        },
    )

    with pytest.raises(
        AnsibleLookupError, match="Several users have a gathered PATH"
    ) as excinfo:
        lookup.run(["ls"], None)

    assert "'root'" in str(excinfo.value)
    assert "'o0-o'" in str(excinfo.value)


@pytest.mark.parametrize(
    "users",
    [
        {},
        {"1000": {"name": "o0-o", "uid": 1000}},
        {"1000": {"name": "o0-o", "uid": 1000, "environment": {}}},
        {
            "1000": {
                "name": "o0-o",
                "uid": 1000,
                "environment": {"PATH": None},
            }
        },
        {"1000": None},
    ],
)
def test_a_namespace_with_no_gathered_path_answers_unknown(
    make_lookup, users: dict[str, Any]
) -> None:
    """Test that an ungathered search path is an unknown order, not
    an empty one."""

    lookup = make_lookup(o0_paths={"/bin/ls": INFERRED}, o0_users=users)

    assert lookup.run(["ls"], None) == [{"command": "ls", "state": "unknown"}]


def test_an_unknown_user_answers_unknown(make_lookup) -> None:
    """Test that a user with no entry lends no search path."""

    lookup = make_lookup(o0_paths={"/bin/ls": INFERRED}, o0_users=USERS)

    assert lookup.run(["ls"], None, user="nobody") == [
        {"command": "ls", "state": "unknown"}
    ]


# ---------------------------------------------------------------------
# A host that gathered nothing
# ---------------------------------------------------------------------


def test_a_host_that_gathered_nothing_answers_unknown_for_every_name(
    make_lookup,
) -> None:
    """Test that an empty namespace was never asked anything."""

    lookup = make_lookup()

    assert lookup.run(["ls", "awk", "doas"], None) == [
        {"command": "ls", "state": "unknown"},
        {"command": "awk", "state": "unknown"},
        {"command": "doas", "state": "unknown"},
    ]


def test_a_gathered_path_without_a_store_answers_unknown(
    make_lookup,
) -> None:
    """Test that a search order with nothing gathered along it stays
    unknown."""

    lookup = make_lookup(o0_users=USERS)

    assert lookup.run(["ls"], None) == [{"command": "ls", "state": "unknown"}]


def test_another_host_s_facts_answer_for_it(make_lookup) -> None:
    """Test that host reads the store out of that host's vars."""

    lookup = make_lookup(
        o0_paths={"/bin/nft": None},
        o0_users=USERS,
        hostvars={
            "firewall1": {
                "o0_paths": {"/usr/sbin/nft": INFERRED},
                "o0_users": {
                    "0": {
                        "name": "root",
                        "uid": 0,
                        "environment": {"PATH": "/usr/sbin"},
                    }
                },
            }
        },
    )

    assert lookup.run(["nft"], None, host="firewall1") == [
        {
            "command": "nft",
            "state": "resolved",
            "path": "/usr/sbin/nft",
        }
    ]


def test_a_host_that_gathered_nothing_answers_unknown(
    make_lookup,
) -> None:
    """Test that another host's empty namespace answers unknown."""

    lookup = make_lookup(
        o0_paths={"/bin/nft": INFERRED},
        o0_users=USERS,
        hostvars={"firewall1": {}},
    )

    assert lookup.run(["nft"], None, host="firewall1") == [
        {"command": "nft", "state": "unknown"}
    ]


# ---------------------------------------------------------------------
# Search path entries no store can key
# ---------------------------------------------------------------------


@pytest.mark.parametrize("entry, error_text", INVALID_ENTRIES)
def test_strict_fails_on_an_entry_that_keys_nothing(
    gathered, entry: Any, error_text: str
) -> None:
    """Test that the default refuses a search path it cannot
    follow."""

    lookup = gathered({"/bin/ls": INFERRED})

    with pytest.raises(AnsibleLookupError, match=error_text):
        lookup.run(["ls"], None, path=[entry, "/bin"])


@pytest.mark.parametrize("entry, error_text", INVALID_ENTRIES)
def test_warn_drops_the_entry_and_says_so(
    gathered, entry: Any, error_text: str
) -> None:
    """Test that a warned-about entry is skipped and the rest of the
    search runs."""

    lookup = gathered({"/bin/ls": INFERRED})

    assert lookup.run(
        ["ls"], None, path=[entry, "/bin"], path_errors="warn"
    ) == [{"command": "ls", "state": "resolved", "path": "/bin/ls"}]

    lookup._display.warning.assert_called_once()
    assert error_text in lookup._display.warning.call_args[0][0]


@pytest.mark.parametrize("entry, error_text", INVALID_ENTRIES)
def test_ignore_drops_the_entry_silently(
    gathered, entry: Any, error_text: str
) -> None:
    """Test that an ignored entry costs neither a failure nor a
    warning."""

    lookup = gathered({"/bin/ls": INFERRED})

    assert lookup.run(
        ["ls"], None, path=[entry, "/bin"], path_errors="ignore"
    ) == [{"command": "ls", "state": "resolved", "path": "/bin/ls"}]

    lookup._display.warning.assert_not_called()


@pytest.mark.parametrize(
    "path",
    [":/bin", "/bin:", "/bin::/usr/bin", ""],
)
def test_a_stray_separator_writes_an_empty_entry(gathered, path: str) -> None:
    """Test that a leading, trailing, or doubled ':' is one empty
    entry rather than nothing at all."""

    lookup = gathered({"/bin/ls": INFERRED, "/usr/bin/ls": INFERRED})

    with pytest.raises(AnsibleLookupError, match="is not an absolute path"):
        lookup.run(["ls"], None, path=path)


def test_a_gathered_entry_that_keys_nothing_is_refused_too(
    make_lookup,
) -> None:
    """Test that the gathered PATH is held to the same keys as a
    supplied one."""

    lookup = make_lookup(
        o0_paths={"/bin/ls": INFERRED},
        o0_users={
            "1000": {
                "name": "o0-o",
                "uid": 1000,
                "environment": {"PATH": "/bin:~/bin"},
            }
        },
    )

    with pytest.raises(AnsibleLookupError, match="is not an absolute path"):
        lookup.run(["ls"], None)


def test_every_unusable_entry_is_warned_about(gathered) -> None:
    """Test that dropping one entry does not excuse the next."""

    lookup = gathered({"/bin/ls": INFERRED})

    lookup.run(
        ["ls"],
        None,
        path=["bin", "~/bin", "/bin"],
        path_errors="warn",
    )

    assert lookup._display.warning.call_count == 2


@pytest.mark.parametrize("path_errors", ["", "quiet", "STRICT", None, 1])
def test_path_errors_takes_one_of_three_words(
    gathered, path_errors: Any
) -> None:
    """Test that an unrecognized mode fails rather than guessing."""

    lookup = gathered({})

    with pytest.raises(AnsibleLookupError, match="must be one of"):
        lookup.run(["ls"], None, path="/bin", path_errors=path_errors)


@pytest.mark.parametrize("path", [1, 1.5, {"dirs": "/bin"}, {"/bin"}])
def test_a_path_that_is_neither_string_nor_list_is_refused(
    gathered, path: Any
) -> None:
    """Test that only the two forms a search path takes are read."""

    lookup = gathered({})

    with pytest.raises(
        AnsibleLookupError, match="must be a ':'-separated search path"
    ):
        lookup.run(["ls"], None, path=path)


def test_a_path_emptied_by_dropped_entries_resolves_nothing(
    gathered,
) -> None:
    """Test that a search path every entry was dropped from is the
    empty search path, which nothing can be found in."""

    lookup = gathered({"/bin/ls": INFERRED})

    assert lookup.run(["ls"], None, path="~/bin", path_errors="ignore") == [
        {"command": "ls", "state": "missing", "path": None}
    ]


# ---------------------------------------------------------------------
# The working directory a legacy entry resolves against
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "entry, candidate",
    [
        ("bin", "/srv/bin/ls"),
        ("./bin", "/srv/bin/ls"),
        ("../bin", "/bin/ls"),
        (".", "/srv/ls"),
        ("..", "/ls"),
        ("", "/srv/ls"),
        ("~", "/srv/~/ls"),
        ("~/bin", "/srv/~/bin/ls"),
    ],
)
def test_cwd_resolves_an_entry_the_way_the_process_would(
    gathered, entry: str, candidate: str
) -> None:
    """Test that a relative entry joins the working directory, and
    that '~' joins as a literal path component."""

    lookup = gathered({candidate: INFERRED})

    assert lookup.run(["ls"], None, path=[entry], cwd="/srv") == [
        {"command": "ls", "state": "resolved", "path": candidate}
    ]


def test_cwd_resolves_the_empty_entry_a_stray_separator_writes(
    gathered,
) -> None:
    """Test that the empty entry searches the working directory
    itself."""

    lookup = gathered({"/srv/ls": INFERRED, "/bin/ls": INFERRED})

    assert lookup.run(["ls"], None, path=":/bin", cwd="/srv") == [
        {"command": "ls", "state": "resolved", "path": "/srv/ls"}
    ]


def test_cwd_leaves_an_absolute_entry_alone(gathered) -> None:
    """Test that a working directory does not reach an entry that
    names its own directory."""

    lookup = gathered({"/bin/ls": INFERRED, "/srv/bin/ls": INFERRED})

    assert lookup.run(["ls"], None, path="/bin", cwd="/srv") == [
        {"command": "ls", "state": "resolved", "path": "/bin/ls"}
    ]


def test_cwd_does_not_excuse_an_entry_that_is_not_a_string(
    gathered,
) -> None:
    """Test that a working directory lends nothing to a non-string
    entry."""

    lookup = gathered({"/bin/ls": INFERRED})

    with pytest.raises(AnsibleLookupError, match="is not a string"):
        lookup.run(["ls"], None, path=[1, "/bin"], cwd="/srv")


@pytest.mark.parametrize("cwd", ["srv", "./srv", "~", "", 1, ["/srv"]])
def test_cwd_must_be_an_absolute_path(gathered, cwd: Any) -> None:
    """Test that the caller's own argument names a directory."""

    lookup = gathered({})

    with pytest.raises(AnsibleLookupError, match="must be an absolute path"):
        lookup.run(["ls"], None, path="/bin", cwd=cwd)


@pytest.mark.parametrize("path_errors", ["strict", "warn", "ignore"])
def test_cwd_is_held_strictly_whatever_path_errors_says(
    gathered, path_errors: str
) -> None:
    """Test that path_errors softens gathered entries, not the
    argument."""

    lookup = gathered({})

    with pytest.raises(AnsibleLookupError, match="must be an absolute path"):
        lookup.run(
            ["ls"], None, path="/bin", cwd="srv", path_errors=path_errors
        )


def test_cwd_is_keyed_canonically(gathered) -> None:
    """Test that a loosely written working directory still keys the
    store."""

    lookup = gathered({"/srv/bin/ls": INFERRED})

    assert lookup.run(["ls"], None, path=["bin"], cwd="/srv/project/..") == [
        {"command": "ls", "state": "resolved", "path": "/srv/bin/ls"}
    ]


def test_without_cwd_a_relative_entry_is_an_error(gathered) -> None:
    """Test that an entry naming nothing a store can key fails."""

    lookup = gathered({"/bin/ls": INFERRED})

    with pytest.raises(
        AnsibleLookupError, match="which a fact store has none of"
    ):
        lookup.run(["ls"], None, path="/bin:.")


# ---------------------------------------------------------------------
# Terms a search path does not apply to
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "term",
    ["/bin/ls", "./ls", "../ls", "bin/ls", "ls/"],
)
def test_a_term_carrying_a_separator_is_refused(gathered, term: str) -> None:
    """Test that a path is not a name the search path applies to."""

    lookup = gathered({})

    with pytest.raises(AnsibleLookupError, match="A name carrying a"):
        lookup.run([term], None)


@pytest.mark.parametrize("term", [".", ".."])
def test_a_term_naming_no_file_of_its_own_is_refused(
    gathered, term: str
) -> None:
    """Test that the dot entries are not command names."""

    lookup = gathered({})

    with pytest.raises(AnsibleLookupError, match="names no file of its own"):
        lookup.run([term], None)


@pytest.mark.parametrize("term", ["", None, 1, ["ls"], {"ls": True}])
def test_a_term_that_is_not_a_command_name_is_refused(
    gathered, term: Any
) -> None:
    """Test that only a non-empty string names a command."""

    lookup = gathered({})

    with pytest.raises(AnsibleLookupError, match="must be a command name"):
        lookup.run([term], None)


# ---------------------------------------------------------------------
# Facts that are not what they claim to be
# ---------------------------------------------------------------------


@pytest.mark.parametrize("paths", ["/bin/ls", ["/bin/ls"], 1, {"/bin"}])
def test_an_o0_paths_fact_that_is_not_a_dictionary_fails(
    make_lookup, paths: Any
) -> None:
    """Test that a store that is not a mapping is an error, not an
    unknown."""

    lookup = make_lookup(o0_paths=paths, o0_users=USERS)

    with pytest.raises(
        AnsibleLookupError,
        match="'o0_paths' fact is not a dictionary",
    ):
        lookup.run(["ls"], None)


@pytest.mark.parametrize("users", ["o0-o", ["o0-o"], 1])
def test_an_o0_users_fact_that_is_not_a_dictionary_fails(
    make_lookup, users: Any
) -> None:
    """Test that the users fact is held to its shape as well."""

    lookup = make_lookup(o0_paths={}, o0_users=users)

    with pytest.raises(
        AnsibleLookupError,
        match="'o0_users' fact is not a dictionary",
    ):
        lookup.run(["ls"], None)


@pytest.mark.parametrize("entry", ["/bin/ls", ["executable"], 1, True])
def test_a_store_entry_that_is_neither_null_nor_a_mapping_fails(
    gathered, entry: Any
) -> None:
    """Test that an entry the absence contract does not allow
    raises."""

    lookup = gathered({"/usr/local/bin/ls": entry})

    with pytest.raises(AnsibleLookupError, match="neither null nor a mapping"):
        lookup.run(["ls"], None)


def test_a_malformed_entry_beyond_the_answer_is_never_reached(
    gathered,
) -> None:
    """Test that the search stops where it resolves, malformed
    entries behind it and all."""

    lookup = gathered(
        {"/usr/local/bin/ls": INFERRED, "/usr/bin/ls": "nonsense"}
    )

    assert lookup.run(["ls"], None) == [
        {
            "command": "ls",
            "state": "resolved",
            "path": "/usr/local/bin/ls",
        }
    ]


# ---------------------------------------------------------------------
# Canonical keys
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "path, canonical",
    [
        ("/", "/"),
        ("//", "/"),
        ("///usr/bin", "/usr/bin"),
        ("/usr/bin", "/usr/bin"),
        ("/usr/bin/", "/usr/bin"),
        ("/usr//bin", "/usr/bin"),
        ("/usr/./bin", "/usr/bin"),
        ("/usr/local/../bin", "/usr/bin"),
        ("/usr/bin/..", "/usr"),
        ("/..", "/"),
        ("/srv/~/bin", "/srv/~/bin"),
        ("/srv/Application Support", "/srv/Application Support"),
    ],
)
def test_canonicalize_reduces_a_path_to_the_key_the_store_uses(
    path: str, canonical: str
) -> None:
    """Test that a path keys the store by what it is rather than by
    how it was written."""

    assert canonicalize(path) == canonical
