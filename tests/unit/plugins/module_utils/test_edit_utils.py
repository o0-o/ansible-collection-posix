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

"""Unit tests for the pure line and block editing engines."""

from __future__ import annotations

import re

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils.edit_utils import (
    ensure_block,
    ensure_line,
    remove_block,
    remove_lines,
)

BEGIN = "# BEGIN ANSIBLE MANAGED BLOCK"
END = "# END ANSIBLE MANAGED BLOCK"


@pytest.mark.parametrize(
    "lines, kwargs, expected_lines, expected_msg",
    [
        # Nothing matches, so the line lands at EOF
        (
            ["a", "b"],
            {"line": "c"},
            ["a", "b", "c"],
            "line added",
        ),
        # BOF puts the line first
        (
            ["a", "b"],
            {"line": "c", "insertbefore": "BOF"},
            ["c", "a", "b"],
            "line added",
        ),
        # regexp replaces the last match and dedupes the first
        (
            ["foo=1", "bar", "foo=2"],
            {"line": "foo=9", "regexp": "^foo="},
            ["bar", "foo=9"],
            "line replaced 1 line deduped",
        ),
        # firstmatch replaces the first match and dedupes the last
        (
            ["foo=1", "bar", "foo=2"],
            {"line": "foo=9", "regexp": "^foo=", "firstmatch": True},
            ["foo=9", "bar"],
            "line replaced 1 line deduped",
        ),
        # search_string replaces the one line holding the text
        (
            ["# comment", "PermitRootLogin yes", "other"],
            {
                "line": "PermitRootLogin no",
                "search_string": "PermitRootLogin",
            },
            ["# comment", "PermitRootLogin no", "other"],
            "line replaced",
        ),
        # search_string dedupes like regexp does
        (
            ["k=1", "other", "k=2"],
            {"line": "k=9", "search_string": "k="},
            ["other", "k=9"],
            "line replaced 1 line deduped",
        ),
        # backrefs expand the match into the replacement
        (
            ["foo=1", "keep"],
            {
                "line": r"bar=\1",
                "regexp": r"^foo=(\d+)$",
                "backrefs": True,
            },
            ["bar=1", "keep"],
            "line replaced",
        ),
        # A regexp that matches nothing appends the line literally,
        # backreference syntax and all
        (
            ["a"],
            {
                "line": r"bar=\1",
                "regexp": r"^zzz=(\d+)$",
                "backrefs": True,
            },
            ["a", r"bar=\1"],
            "line added",
        ),
        # insertafter anchors below the matching line
        (
            ["a", "anchor", "b"],
            {"line": "new", "insertafter": "^anchor"},
            ["a", "anchor", "new", "b"],
            "line added",
        ),
        # insertbefore anchors above the matching line
        (
            ["a", "anchor", "b"],
            {"line": "new", "insertbefore": "^anchor"},
            ["a", "new", "anchor", "b"],
            "line added",
        ),
        # The exact line is already present: nothing is added or
        # replaced, so the message carries only the dedupe tally
        (
            ["a", "b"],
            {"line": "a"},
            ["a", "b"],
            "",
        ),
        # ... and with dedupe off there is no message at all
        (
            ["a", "b"],
            {"line": "a", "dedupe": False},
            ["a", "b"],
            "",
        ),
        # Duplicate literal lines: the last instance survives
        (
            ["a", "b", "a"],
            {"line": "a"},
            ["b", "a"],
            "1 line deduped",
        ),
        # ... and firstmatch keeps the first instead
        (
            ["a", "b", "a"],
            {"line": "a", "firstmatch": True},
            ["a", "b"],
            "1 line deduped",
        ),
        # dedupe=False leaves the duplicates alone
        (
            ["a", "b", "a"],
            {"line": "a", "dedupe": False},
            ["a", "b", "a"],
            "",
        ),
        # dedupe=False also drops the tally from an insert message
        (
            ["a", "b"],
            {"line": "c", "dedupe": False},
            ["a", "b", "c"],
            "line added",
        ),
        # The line exists but not at its anchor, so a copy is inserted
        # at index 0 and the stale copy at index 1 is deduped as index
        # 2. The donor treated a keep index of 0 as unset here and
        # deleted the anchor instead of the stale copy.
        (
            ["anchor", "a"],
            {"line": "a", "insertbefore": "^anchor"},
            ["a", "anchor"],
            "line added 1 line deduped",
        ),
        # The same shift below an insertafter anchor
        (
            ["a", "anchor", "b"],
            {"line": "a", "insertafter": "^anchor"},
            ["anchor", "a", "b"],
            "line added 1 line deduped",
        ),
    ],
)
def test_ensure_line_computes_new_lines(
    lines, kwargs, expected_lines, expected_msg
) -> None:
    """Test ensure_line returns the edited lines and its message."""

    new_lines, msg = ensure_line(lines, **kwargs)

    assert new_lines == expected_lines
    assert msg == expected_msg


def test_ensure_line_leaves_the_input_alone() -> None:
    """Test ensure_line copies rather than editing in place."""

    lines = ["a", "b", "a"]

    new_lines, _msg = ensure_line(lines, "a")

    assert lines == ["a", "b", "a"]
    assert new_lines == ["b", "a"]


@pytest.mark.parametrize(
    "lines, kwargs, expected_error",
    [
        (
            ["a"],
            {"line": "b", "regexp": "["},
            "Invalid regexp pattern: [",
        ),
        (
            ["a"],
            {"line": "b", "insertafter": "["},
            "Invalid insertafter pattern: [",
        ),
        (
            ["a"],
            {"line": "b", "insertbefore": "["},
            "Invalid insertbefore pattern: [",
        ),
        # An empty insertafter compiles and anchors on every line, but
        # it is falsy, so neither the keep nor the insert branch fires
        (
            ["a", "b"],
            {"line": "a", "insertafter": ""},
            "No lines found, added or replaced",
        ),
    ],
)
def test_ensure_line_rejects_bad_input(lines, kwargs, expected_error) -> None:
    """Test ensure_line raises ValueError naming the bad input."""

    with pytest.raises(ValueError, match=re.escape(expected_error)):
        ensure_line(lines, **kwargs)


@pytest.mark.parametrize(
    "lines, kwargs, expected_lines, expected_count",
    [
        # An exact line matches after its line ending is stripped
        (["a\n", "b\n"], {"line": "a"}, ["b\n"], 1),
        # ... but only as a whole line, never as a substring
        (["ab\n"], {"line": "a"}, ["ab\n"], 0),
        # A regexp removes every match
        (
            ["foo", "bar", "foobar"],
            {"regexp": "^foo"},
            ["bar"],
            2,
        ),
        # search_string matches anywhere in the line
        (["alpha", "beta"], {"search_string": "lph"}, ["beta"], 1),
        # Nothing matches, so nothing is removed
        (["a", "b"], {"regexp": "^zzz"}, ["a", "b"], 0),
    ],
)
def test_remove_lines_drops_matches(
    lines, kwargs, expected_lines, expected_count
) -> None:
    """Test remove_lines returns the kept lines and a removal count."""

    new_lines, removed = remove_lines(lines, **kwargs)

    assert new_lines == expected_lines
    assert removed == expected_count


def test_remove_lines_rejects_bad_regexp() -> None:
    """Test remove_lines raises ValueError naming the bad pattern."""

    with pytest.raises(
        ValueError, match=re.escape("Invalid regexp pattern: [")
    ):
        remove_lines(["a"], regexp="[")


@pytest.mark.parametrize(
    "lines, block, kwargs, expected_lines, expected_msg",
    [
        # No pair yet, so the block is appended
        (
            ["a"],
            "x\ny",
            {},
            ["a", BEGIN, "x", "y", END],
            "block added",
        ),
        # An explicit EOF anchor appends too
        (
            ["a"],
            "x",
            {"insertafter": "EOF"},
            ["a", BEGIN, "x", END],
            "block added",
        ),
        # BOF puts the block first
        (
            ["a"],
            "x",
            {"insertbefore": "BOF"},
            [BEGIN, "x", END, "a"],
            "block added",
        ),
        # insertafter anchors below the last matching line
        (
            ["a", "anchor", "b"],
            "x",
            {"insertafter": "^anchor"},
            ["a", "anchor", BEGIN, "x", END, "b"],
            "block added",
        ),
        # insertbefore anchors above the last matching line
        (
            ["a", "anchor", "b"],
            "x",
            {"insertbefore": "^anchor"},
            ["a", BEGIN, "x", END, "anchor", "b"],
            "block added",
        ),
        # An existing pair is replaced in place, surroundings intact
        (
            ["head", BEGIN, "old", END, "tail"],
            "new1\nnew2",
            {},
            ["head", BEGIN, "new1", "new2", END, "tail"],
            "block replaced",
        ),
        # Markers are matched ignoring indentation, and the rewritten
        # pair comes back flush left
        (
            ["  " + BEGIN, "old", "\t" + END],
            "new",
            {},
            [BEGIN, "new", END],
            "block replaced",
        ),
        # Drift collapses: the first pair is rewritten and every later
        # pair is removed, counted in the message
        (
            ["head", BEGIN, "o1", "o2", END, "mid", BEGIN, "p", END, "tail"],
            "new",
            {},
            ["head", BEGIN, "new", END, "mid", "tail"],
            "block replaced (1 duplicate blocks deduped)",
        ),
        # An empty block removes the managed region entirely
        (
            ["head", BEGIN, "old", END, "tail"],
            "",
            {},
            ["head", "tail"],
            "1 block removed",
        ),
        # A custom template and custom begin and end texts
        (
            ["a"],
            "x",
            {
                "marker": "// {mark} custom",
                "marker_begin": "START",
                "marker_end": "STOP",
            },
            ["a", "// START custom", "x", "// STOP custom"],
            "block added",
        ),
    ],
)
def test_ensure_block_computes_new_lines(
    lines, block, kwargs, expected_lines, expected_msg
) -> None:
    """Test ensure_block returns the edited lines and its message."""

    new_lines, msg = ensure_block(lines, block, **kwargs)

    assert new_lines == expected_lines
    assert msg == expected_msg


@pytest.mark.parametrize(
    "lines, kwargs, expected_lines, expected_msg",
    [
        (
            ["head", BEGIN, "old", END, "tail"],
            {},
            ["head", "tail"],
            "1 block removed",
        ),
        # Every pair goes, and the plural agrees with the count
        (
            [BEGIN, "a", END, "mid", BEGIN, "b", END],
            {},
            ["mid"],
            "2 blocks removed",
        ),
        (
            ["a", "b"],
            {},
            ["a", "b"],
            "no block found",
        ),
        (
            ["h", "// START custom", "x", "// STOP custom", "t"],
            {
                "marker": "// {mark} custom",
                "marker_begin": "START",
                "marker_end": "STOP",
            },
            ["h", "t"],
            "1 block removed",
        ),
    ],
)
def test_remove_block_drops_pairs(
    lines, kwargs, expected_lines, expected_msg
) -> None:
    """Test remove_block returns the kept lines and its message."""

    new_lines, msg = remove_block(lines, **kwargs)

    assert new_lines == expected_lines
    assert msg == expected_msg


@pytest.mark.parametrize(
    "call",
    [
        lambda lines, **kwargs: ensure_block(lines, "x", **kwargs),
        remove_block,
    ],
    ids=["ensure_block", "remove_block"],
)
@pytest.mark.parametrize(
    "lines, kwargs, expected_error",
    [
        (["a"], {"marker": "# BLOCK"}, "marker must contain '{mark}'"),
        (
            ["a"],
            {
                "marker": "# {mark}",
                "marker_begin": "X",
                "marker_end": "X",
            },
            "begin and end markers must differ",
        ),
        ([BEGIN, "x"], {}, "Begin marker without end marker at line 1"),
        ([END], {}, "End marker without begin marker at line 1"),
        (
            [BEGIN, BEGIN, END],
            {},
            "Nested or unclosed begin marker at line 1",
        ),
    ],
)
def test_block_functions_reject_bad_markers(
    call, lines, kwargs, expected_error
) -> None:
    """Test both block functions raise on unusable marker state."""

    with pytest.raises(ValueError, match=re.escape(expected_error)):
        call(lines, **kwargs)


@pytest.mark.parametrize(
    "kwargs, expected_error",
    [
        ({"insertafter": "["}, "Invalid insertafter pattern: ["),
        ({"insertbefore": "["}, "Invalid insertbefore pattern: ["),
    ],
)
def test_ensure_block_rejects_bad_anchors(kwargs, expected_error) -> None:
    """Test ensure_block raises ValueError naming the bad pattern."""

    with pytest.raises(ValueError, match=re.escape(expected_error)):
        ensure_block(["a"], "x", **kwargs)
