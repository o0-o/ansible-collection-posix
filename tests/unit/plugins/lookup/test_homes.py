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

"""Unit tests for the homes lookup plugin."""

from __future__ import annotations

from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from ansible.errors import AnsibleLookupError

from ansible_collections.o0_o.posix.plugins.lookup.homes import LookupModule

# What the users subset files at a home's own path: the metadata the
# read returned, the home tag, and the UIDs that call it home
ROOT_HOME = {
    "type": "directory",
    "uid": 0,
    "gid": 0,
    "tags": ["posix", "home"],
    "residents": [0],
}
USER_HOME = {
    "type": "directory",
    "uid": 1000,
    "gid": 20,
    "tags": ["posix", "home"],
    "residents": [1000],
}

USERS = {
    "0": {"name": "root", "uid": 0, "gid": 0, "home": "/var/root"},
    "1000": {"name": "o0-o", "uid": 1000, "gid": 20, "home": "/home/o0-o"},
}


class FakeTemplar:
    """Stand in for the templar a lookup reads variables through.

    ``lookup_var`` reads ``available_variables`` and ``run`` templates
    every term, so those two are the whole of the seam.
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
def joined(make_lookup):
    """Build a lookup joining the sample users against a store.

    :returns: A factory taking the o0_paths store
    """

    def _make(paths: dict[str, Any]) -> LookupModule:
        return make_lookup(o0_users=USERS, o0_paths=paths)

    return _make


# ---------------------------------------------------------------------
# The four states
# ---------------------------------------------------------------------


def test_a_home_the_store_describes_is_present(joined) -> None:
    """Test that a described home answers with what was observed."""

    lookup = joined({"/home/o0-o": USER_HOME})

    assert lookup.run(["o0-o"], None) == [
        {
            "uid": 1000,
            "name": "o0-o",
            "home": "/home/o0-o",
            "state": "present",
            "path": "/home/o0-o",
            "residents": [1000],
            "entry": USER_HOME,
        }
    ]


def test_a_home_the_store_holds_as_absent_is_dangling(joined) -> None:
    """Test that a null at a user's home is the dangling home the
    lookup exists to surface, carrying a null entry with it."""

    lookup = joined({"/home/o0-o": None})

    assert lookup.run(["o0-o"], None) == [
        {
            "uid": 1000,
            "name": "o0-o",
            "home": "/home/o0-o",
            "state": "dangling",
            "path": "/home/o0-o",
            "residents": [1000],
            "entry": None,
        }
    ]


def test_an_ungathered_home_carries_no_entry_key_at_all(joined) -> None:
    """Test that a home nobody asked about has no entry key, so it
    cannot be read as a home confirmed to be there or gone."""

    lookup = joined({})

    (answer,) = lookup.run(["o0-o"], None)

    assert answer == {
        "uid": 1000,
        "name": "o0-o",
        "home": "/home/o0-o",
        "state": "unknown",
        "path": "/home/o0-o",
        "residents": [1000],
    }
    assert "entry" not in answer


def test_a_dangling_home_is_never_an_ungathered_one(joined) -> None:
    """Test the distinction the lookup exists to keep: a home the host
    was asked about and lacks is not a home nobody looked for."""

    dangling = joined({"/home/o0-o": None})
    ungathered = joined({})

    (dangling_answer,) = dangling.run(["o0-o"], None)
    (unknown_answer,) = ungathered.run(["o0-o"], None)

    assert dangling_answer["state"] == "dangling"
    assert dangling_answer["entry"] is None
    assert unknown_answer["state"] == "unknown"
    assert "entry" not in unknown_answer


@pytest.mark.parametrize("home", [None, "", "home/o0-o", "../o0-o", 1000])
def test_a_user_naming_no_home_is_unnamed(make_lookup, home: Any) -> None:
    """Test that a passwd field naming no path a store could key is a
    fact about the user rather than an absence in the store."""

    lookup = make_lookup(
        o0_users={"1000": {"name": "o0-o", "uid": 1000, "home": home}},
        o0_paths={"/home/o0-o": USER_HOME},
    )

    (answer,) = lookup.run(["o0-o"], None)

    assert answer == {
        "uid": 1000,
        "name": "o0-o",
        "home": home if isinstance(home, str) and home else None,
        "state": "unnamed",
    }
    assert "path" not in answer
    assert "entry" not in answer


def test_one_call_answers_each_state_in_its_own_shape(make_lookup) -> None:
    """Test that the four answers are told apart without reading the
    state word, by the path and entry keys alone."""

    lookup = make_lookup(
        o0_users={
            "0": {"name": "root", "uid": 0, "home": "/var/root"},
            "1": {"name": "gone", "uid": 1, "home": "/home/gone"},
            "2": {"name": "unasked", "uid": 2, "home": "/home/unasked"},
            "3": {"name": "nowhere", "uid": 3, "home": ""},
        },
        o0_paths={"/var/root": ROOT_HOME, "/home/gone": None},
    )

    states = [answer["state"] for answer in lookup.run([], None)]

    assert states == ["present", "dangling", "unknown", "unnamed"]


# ---------------------------------------------------------------------
# The audit view
# ---------------------------------------------------------------------


def test_no_terms_answers_for_every_user(joined) -> None:
    """Test that the audit view answers for the whole passwd file."""

    lookup = joined({"/var/root": ROOT_HOME, "/home/o0-o": None})

    answers = lookup.run([], None)

    assert [answer["name"] for answer in answers] == ["root", "o0-o"]
    assert [answer["state"] for answer in answers] == ["present", "dangling"]


def test_the_audit_reads_in_numeric_uid_order(make_lookup) -> None:
    """Test that users are answered for in UID order rather than in
    the order the stringified keys sort in."""

    lookup = make_lookup(
        o0_users={
            "1000": {"name": "o0-o", "uid": 1000, "home": "/home/o0-o"},
            "0": {"name": "root", "uid": 0, "home": "/var/root"},
            "99": {"name": "mid", "uid": 99, "home": "/home/mid"},
        },
        o0_paths={},
    )

    assert [answer["uid"] for answer in lookup.run([], None)] == [0, 99, 1000]


def test_a_user_with_no_uid_is_answered_for_last(make_lookup) -> None:
    """Test that an entry carrying no UID still gets an answer, at the
    end, rather than breaking the ordering."""

    lookup = make_lookup(
        o0_users={
            "nobody": {"name": "nobody", "home": "/home/nobody"},
            "0": {"name": "root", "uid": 0, "home": "/var/root"},
        },
        o0_paths={},
    )

    answers = lookup.run([], None)

    assert [answer["uid"] for answer in answers] == [0, None]


def test_a_users_entry_that_is_not_a_user_is_passed_over(
    make_lookup,
) -> None:
    """Test that a value which is not a mapping is not a user, so the
    audit skips it rather than answering nonsense about it."""

    lookup = make_lookup(
        o0_users={
            "0": {"name": "root", "uid": 0, "home": "/var/root"},
            "junk": "not a user",
        },
        o0_paths={},
    )

    assert [answer["uid"] for answer in lookup.run([], None)] == [0]


def test_a_host_that_gathered_nothing_has_nobody_to_audit(
    make_lookup,
) -> None:
    """Test that an audit of a namespace with no users answers with
    nothing, rather than inventing users to answer about."""

    lookup = make_lookup()

    assert lookup.run([], None) == []


def test_a_gathered_users_fact_with_no_store_is_all_unknown(
    make_lookup,
) -> None:
    """Test that users gathered without any path store answer unknown
    throughout, which is not a clean audit."""

    lookup = make_lookup(o0_users=USERS)

    answers = lookup.run([], None)

    assert [answer["state"] for answer in answers] == ["unknown", "unknown"]
    assert all("entry" not in answer for answer in answers)


# ---------------------------------------------------------------------
# Naming users
# ---------------------------------------------------------------------


@pytest.mark.parametrize("term", ["o0-o", 1000])
def test_a_user_can_be_named_by_uid_or_by_name(joined, term: Any) -> None:
    """Test that either way of naming a user answers for that user."""

    lookup = joined({"/home/o0-o": USER_HOME})

    assert lookup.run([term], None)[0]["uid"] == 1000


def test_every_user_asked_for_is_answered_in_order(joined) -> None:
    """Test that the answers line up with the terms one for one."""

    lookup = joined({"/var/root": ROOT_HOME})

    answers = lookup.run(["o0-o", 0, "root", 1000], None)

    assert [answer["uid"] for answer in answers] == [1000, 0, 0, 1000]


def test_a_term_is_templated_before_it_is_resolved(make_lookup) -> None:
    """Test that a term is run through the templar first."""

    lookup = make_lookup(
        substitutions={"{{ who }}": "o0-o"},
        o0_users=USERS,
        o0_paths={},
    )

    assert lookup.run(["{{ who }}"], None)[0]["uid"] == 1000


def test_a_term_naming_no_user_fails(joined) -> None:
    """Test that a name which is not a user asks about nothing, and
    says so rather than answering."""

    lookup = joined({})

    with pytest.raises(AnsibleLookupError, match="No user 'ghost'"):
        lookup.run(["ghost"], None)


def test_a_term_on_an_ungathered_namespace_says_so(make_lookup) -> None:
    """Test that a named user with no users fact at all is told the
    fact was never gathered, rather than that the user is absent."""

    lookup = make_lookup()

    with pytest.raises(AnsibleLookupError, match="no 'o0_users' fact"):
        lookup.run(["o0-o"], None)


@pytest.mark.parametrize("term", [None, True, 1.5, ["o0-o"], {"uid": 0}])
def test_a_term_that_is_neither_uid_nor_name_is_refused(
    joined, term: Any
) -> None:
    """Test that a term which names a user no way at all is an error."""

    lookup = joined({})

    with pytest.raises(AnsibleLookupError, match="must be a UID or a"):
        lookup.run([term], None)


# ---------------------------------------------------------------------
# How a home keys the store
# ---------------------------------------------------------------------


def test_a_home_is_read_at_the_key_the_store_files_it_under(
    make_lookup,
) -> None:
    """Test that a passwd entry's spelling still finds the path it
    names, because the store keys a path by what it is."""

    lookup = make_lookup(
        o0_users={
            "1000": {"name": "o0-o", "uid": 1000, "home": "/home/o0-o/"}
        },
        o0_paths={"/home/o0-o": USER_HOME},
    )

    (answer,) = lookup.run(["o0-o"], None)

    assert answer["home"] == "/home/o0-o/"
    assert answer["path"] == "/home/o0-o"
    assert answer["state"] == "present"


def test_two_users_sharing_a_home_each_get_an_answer(make_lookup) -> None:
    """Test that a shared home answers once per resident, both naming
    the one path the store keys it under."""

    shared = {
        "type": "directory",
        "tags": ["posix", "home"],
        "residents": [0, 1],
    }
    lookup = make_lookup(
        o0_users={
            "0": {"name": "a", "uid": 0, "home": "/shared"},
            "1": {"name": "b", "uid": 1, "home": "/shared/"},
        },
        o0_paths={"/shared": shared},
    )

    answers = lookup.run([], None)

    assert [answer["path"] for answer in answers] == ["/shared", "/shared"]
    assert all(answer["entry"]["residents"] == [0, 1] for answer in answers)


def test_the_answer_does_not_share_the_store_s_entry(make_lookup) -> None:
    """Test that a caller mutating the answer does not rewrite the
    fact the answer was read from."""

    paths = {"/home/o0-o": {"type": "directory"}}
    lookup = make_lookup(
        o0_users={"1000": {"name": "o0-o", "uid": 1000, "home": "/home/o0-o"}},
        o0_paths=paths,
    )

    (answer,) = lookup.run(["o0-o"], None)
    answer["entry"]["type"] = "link"

    assert paths["/home/o0-o"]["type"] == "directory"


# ---------------------------------------------------------------------
# What the lookup refuses
# ---------------------------------------------------------------------


def test_a_users_fact_that_is_not_a_dictionary_fails(make_lookup) -> None:
    """Test that an o0_users which is not the canonical mapping is an
    error rather than an audit of nothing."""

    lookup = make_lookup(o0_users=["root"])

    with pytest.raises(AnsibleLookupError, match="'o0_users' fact is not"):
        lookup.run([], None)


def test_a_store_that_is_not_a_dictionary_fails(make_lookup) -> None:
    """Test that an o0_paths which is not a store is an error."""

    lookup = make_lookup(o0_users=USERS, o0_paths=["/home/o0-o"])

    with pytest.raises(AnsibleLookupError, match="'o0_paths' fact is not"):
        lookup.run([], None)


def test_an_entry_that_is_neither_null_nor_a_mapping_fails(joined) -> None:
    """Test that an entry the store could not have composed is an
    error rather than an answer read out of it."""

    lookup = joined({"/home/o0-o": "directory"})

    with pytest.raises(AnsibleLookupError, match="neither null nor"):
        lookup.run(["o0-o"], None)


# ---------------------------------------------------------------------
# Reading another host's facts
# ---------------------------------------------------------------------


def test_another_host_s_facts_answer_for_it(make_lookup) -> None:
    """Test that a named host is audited from its own variables."""

    lookup = make_lookup(
        o0_users=USERS,
        o0_paths={"/home/o0-o": USER_HOME},
        hostvars={
            "webserver1": {
                "o0_users": {
                    "1001": {
                        "name": "deploy",
                        "uid": 1001,
                        "home": "/home/deploy",
                    }
                },
                "o0_paths": {"/home/deploy": None},
            }
        },
    )

    assert lookup.run([], None, host="webserver1") == [
        {
            "uid": 1001,
            "name": "deploy",
            "home": "/home/deploy",
            "state": "dangling",
            "path": "/home/deploy",
            "residents": [1001],
            "entry": None,
        }
    ]


def test_a_host_that_gathered_nothing_audits_to_nothing(make_lookup) -> None:
    """Test that a host with no facts of its own has no users to
    answer for, rather than borrowing the running host's."""

    lookup = make_lookup(
        o0_users=USERS,
        o0_paths={"/home/o0-o": USER_HOME},
        hostvars={"webserver1": {}},
    )

    assert lookup.run([], None, host="webserver1") == []


def test_residents_are_derived_rather_than_read_off_the_store(
    make_lookup,
) -> None:
    """Test who lives at a home comes from the users, not the entry.

    The store holds what a path is. Who calls it home is the join
    between these two facts, and a copy of a join kept beside the path
    is a copy that can drift from the field it came out of.
    """
    lookup = make_lookup(
        o0_users={
            "0": {"name": "root", "uid": 0, "home": "/shared"},
            "1000": {"name": "o0-o", "uid": 1000, "home": "/shared/"},
        },
        o0_paths={"/shared": {"type": "directory"}},
    )

    answers = lookup.run([], None)

    assert [answer["residents"] for answer in answers] == [
        [0, 1000],
        [0, 1000],
    ]
    assert "residents" not in answers[0]["entry"]


def test_a_user_who_names_no_home_has_no_residents_key(make_lookup) -> None:
    """Test an unnamed home is a fact about the user rather than an
    absence in the store, so it carries neither a path nor a list of
    who lives at one."""
    lookup = make_lookup(
        o0_users={"1000": {"name": "o0-o", "uid": 1000, "home": ""}},
        o0_paths={},
    )

    (answer,) = lookup.run([], None)

    assert answer["state"] == "unnamed"
    assert "residents" not in answer
    assert "path" not in answer
