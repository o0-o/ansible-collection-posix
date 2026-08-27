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

"""Unit tests for the shells lookup plugin."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from ansible.errors import AnsibleLookupError

from ansible_collections.o0_o.posix.plugins.lookup.shells import LookupModule

# What the users subset files at the shells file's own path: the bytes
# under content, the login shells they name under config
SHELLS = ["/bin/sh", "/bin/zsh"]
PARSED = {"content": "/bin/sh\n/bin/zsh\n", "config": SHELLS}

# A file the host has and names nothing in. It exists and is empty,
# which is not the same answer as never having been read
NAMES_NONE = {"content": "# nothing here\n", "config": []}

# An entry some other producer filed, describing the path without ever
# parsing what is in it
UNPARSED = {"type": "regular", "mode": "0644", "uid": 0, "gid": 0}


class FakeTemplar:
    """Stand in for the templar a lookup reads variables through.

    ``lookup_var`` reads ``available_variables``, and this lookup
    templates nothing, so that one attribute is the whole seam.
    """

    def __init__(self, variables: dict[str, Any]) -> None:
        self.available_variables = variables

    def template(self, value: Any) -> Any:
        """Resolve a value the way the templar would."""
        return value


@pytest.fixture
def make_lookup():
    """Build a lookup reading a namespace the test supplies.

    :returns: A factory taking the namespace as keyword arguments
    """

    def _make(**variables: Any) -> LookupModule:
        lookup = LookupModule(loader=None, templar=FakeTemplar(variables))
        lookup._display = MagicMock()
        return lookup

    return _make


@pytest.fixture
def store(make_lookup):
    """Build a lookup over an o0_paths store the test supplies.

    :returns: A factory taking the store
    """

    def _make(paths: dict[str, Any]) -> LookupModule:
        return make_lookup(o0_paths=paths)

    return _make


# ---------------------------------------------------------------------
# The tri-state answer
# ---------------------------------------------------------------------


def test_a_parsed_file_answers_the_shells_it_names(store) -> None:
    """Test that a parsed shells file answers with what it names."""

    lookup = store({"/etc/shells": PARSED})

    assert lookup.run([], None) == [
        {"path": "/etc/shells", "state": "named", "shells": SHELLS}
    ]


def test_a_file_that_names_none_answers_an_empty_list(store) -> None:
    """Test that a file which exists and lists nothing is named with
    an empty list, because it exists and is empty."""

    lookup = store({"/etc/shells": NAMES_NONE})

    assert lookup.run([], None) == [
        {"path": "/etc/shells", "state": "named", "shells": []}
    ]


def test_a_file_the_store_holds_as_absent_answers_missing(store) -> None:
    """Test that a null at the path is a file confirmed not to be
    there, carrying a null in place of the shells."""

    lookup = store({"/etc/shells": None})

    assert lookup.run([], None) == [
        {"path": "/etc/shells", "state": "missing", "shells": None}
    ]


def test_an_unknown_carries_no_shells_key_at_all(store) -> None:
    """Test that an unknown answer has no shells key to read, so a
    caller cannot mistake it for a host that names none."""

    lookup = store({})

    (answer,) = lookup.run([], None)

    assert answer == {"path": "/etc/shells", "state": "unknown"}
    assert "shells" not in answer


def test_a_path_described_but_never_parsed_is_unknown(store) -> None:
    """Test that an entry carrying no config is an unknown: the file
    is there, and nothing read it."""

    lookup = store({"/etc/shells": UNPARSED})

    (answer,) = lookup.run([], None)

    assert answer == {"path": "/etc/shells", "state": "unknown"}
    assert "shells" not in answer


def test_cannot_say_and_names_none_are_never_spelled_alike(
    store, make_lookup
) -> None:
    """Test the distinction the lookup exists to keep: the store that
    was never asked and the host that names none answer differently."""

    unasked = store({})
    empty = store({"/etc/shells": NAMES_NONE})
    ungathered = make_lookup()

    (unasked_answer,) = unasked.run([], None)
    (empty_answer,) = empty.run([], None)
    (ungathered_answer,) = ungathered.run([], None)

    assert "shells" not in unasked_answer
    assert unasked_answer == ungathered_answer
    assert empty_answer["shells"] == []
    assert unasked_answer != empty_answer


def test_a_host_that_gathered_nothing_answers_unknown(make_lookup) -> None:
    """Test that a namespace with no o0_paths fact was never asked
    anything, rather than being a host that names no login shells."""

    lookup = make_lookup()

    assert lookup.run([], None) == [
        {"path": "/etc/shells", "state": "unknown"}
    ]


def test_the_answer_does_not_share_the_store_s_list(store) -> None:
    """Test that a caller mutating the answer does not rewrite the
    fact the answer was read from."""

    paths = {"/etc/shells": {"config": ["/bin/sh"]}}
    lookup = store(paths)

    (answer,) = lookup.run([], None)
    answer["shells"].append("/bin/zsh")

    assert paths["/etc/shells"]["config"] == ["/bin/sh"]


# ---------------------------------------------------------------------
# The file that is asked about
# ---------------------------------------------------------------------


def test_the_shells_file_is_the_default_question(store) -> None:
    """Test that the lookup asks about /etc/shells unasked."""

    lookup = store(
        {"/etc/shells": PARSED, "/usr/local/etc/shells": NAMES_NONE}
    )

    assert lookup.run([], None)[0]["shells"] == SHELLS


def test_another_file_can_be_named(store) -> None:
    """Test that a producer pointed somewhere else is followed there."""

    lookup = store(
        {"/etc/shells": PARSED, "/usr/local/etc/shells": NAMES_NONE}
    )

    assert lookup.run([], None, path="/usr/local/etc/shells") == [
        {"path": "/usr/local/etc/shells", "state": "named", "shells": []}
    ]


def test_the_file_asked_about_is_keyed_canonically(store) -> None:
    """Test that a path is reduced to the key the store files it
    under, so a spelling answers what the path answers."""

    lookup = store({"/etc/shells": PARSED})

    assert lookup.run([], None, path="/etc/./shells")[0]["shells"] == SHELLS
    assert lookup.run([], None, path="//etc/shells")[0]["shells"] == SHELLS


@pytest.mark.parametrize(
    "path",
    ["etc/shells", "./shells", "~/shells", "", None, 1, ["/etc/shells"]],
)
def test_a_path_that_keys_nothing_is_refused(store, path: Any) -> None:
    """Test that a file named by something no store can key is an
    error rather than an answer about a path it is not."""

    lookup = store({"/etc/shells": PARSED})

    with pytest.raises(AnsibleLookupError, match="must be an absolute path"):
        lookup.run([], None, path=path)


# ---------------------------------------------------------------------
# What the lookup refuses
# ---------------------------------------------------------------------


def test_a_term_is_refused_and_the_path_option_named(store) -> None:
    """Test that a term is an error naming the option that was meant,
    since the question is about one file."""

    lookup = store({"/etc/shells": PARSED})

    with pytest.raises(AnsibleLookupError, match="takes no terms"):
        lookup.run(["/etc/shells"], None)


def test_a_store_that_is_not_a_dictionary_fails(make_lookup) -> None:
    """Test that an o0_paths that is not a store is an error."""

    lookup = make_lookup(o0_paths=["/etc/shells"])

    with pytest.raises(AnsibleLookupError, match="not a dictionary"):
        lookup.run([], None)


def test_an_entry_that_is_neither_null_nor_a_mapping_fails(store) -> None:
    """Test that an entry the store could not have composed is an
    error rather than an answer read out of it."""

    lookup = store({"/etc/shells": "/bin/sh\n"})

    with pytest.raises(AnsibleLookupError, match="neither null nor"):
        lookup.run([], None)


@pytest.mark.parametrize("config", ["/bin/sh", {"0": "/bin/sh"}, 1])
def test_a_config_that_is_not_a_list_fails(store, config: Any) -> None:
    """Test that a config which is not the parsed list of shells is an
    error rather than an answer bent into shape."""

    lookup = store({"/etc/shells": {"config": config}})

    with pytest.raises(AnsibleLookupError, match="not a list of login"):
        lookup.run([], None)


# ---------------------------------------------------------------------
# Reading another host's facts
# ---------------------------------------------------------------------


def test_another_host_s_facts_answer_for_it(make_lookup) -> None:
    """Test that a named host is answered from its own variables."""

    lookup = make_lookup(
        o0_paths={"/etc/shells": NAMES_NONE},
        hostvars={"webserver1": {"o0_paths": {"/etc/shells": PARSED}}},
    )

    assert lookup.run([], None, host="webserver1") == [
        {"path": "/etc/shells", "state": "named", "shells": SHELLS}
    ]


def test_a_host_that_gathered_nothing_answers_unknown_for_itself(
    make_lookup,
) -> None:
    """Test that a host with no facts of its own is unknown rather
    than answered from the host the play is running against."""

    lookup = make_lookup(
        o0_paths={"/etc/shells": PARSED},
        hostvars={"webserver1": {}},
    )

    assert lookup.run([], None, host="webserver1") == [
        {"path": "/etc/shells", "state": "unknown"}
    ]
