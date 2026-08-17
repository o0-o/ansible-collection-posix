# vim: ts=4:sw=4:sts=4:et:ft=python
# -*- mode: python; tab-width: 4; indent-tabs-mode: nil; -*-
#
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later
# (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
#
# Copyright (c) 2025 oØ.o (@o0-o)
#
# Adapted from:
#   - The lineinfile_dedupe action plugin in this collection, itself
#     adapted from the lineinfile module in Ansible core
#     (GPL-3.0-or-later)
#
# This file is part of the o0_o.posix Ansible Collection.

"""Pure line and block editing engines for the write action plugin.

These functions compute new file contents from old contents and edit
parameters. They perform no I/O and hold no plugin state, so the write
action plugin stays a thin dispatcher and the editing logic tests
directly against literal inputs.

The line engine is ported from the lineinfile_dedupe action plugin;
its matching, insertion, replacement, and deduplication behavior is
preserved. Two index comparisons that treated index 0 as "unset" were
corrected to explicit None checks during the port.
"""

from __future__ import annotations

import re
from typing import Optional


def compile_line_patterns(
    regexp: Optional[str],
    insertafter: Optional[str],
    insertbefore: Optional[str],
) -> tuple[Optional[re.Pattern], Optional[re.Pattern]]:
    """Compile the match and insertion regexes for a line edit.

    :param Optional[str] regexp: Pattern matching lines to replace
    :param Optional[str] insertafter: Pattern, 'EOF', or None
    :param Optional[str] insertbefore: Pattern, 'BOF', or None
    :returns tuple[Optional[re.Pattern], Optional[re.Pattern]]:
        (match_re, insert_re), either may be None
    :raises ValueError: If a pattern does not compile
    """
    match_re = None
    insert_re = None

    if regexp:
        try:
            match_re = re.compile(regexp)
        except re.error as e:
            raise ValueError(f"Invalid regexp pattern: {regexp}: {e}")

    if insertafter not in (None, "BOF", "EOF"):
        try:
            insert_re = re.compile(insertafter)
        except re.error as e:
            raise ValueError(
                f"Invalid insertafter pattern: {insertafter}: {e}"
            )
    elif insertbefore not in (None, "BOF"):
        try:
            insert_re = re.compile(insertbefore)
        except re.error as e:
            raise ValueError(
                f"Invalid insertbefore pattern: {insertbefore}: {e}"
            )

    return match_re, insert_re


def ensure_line(
    lines: list[str],
    line: str,
    regexp: Optional[str] = None,
    search_string: Optional[str] = None,
    insertafter: Optional[str] = None,
    insertbefore: Optional[str] = None,
    firstmatch: bool = False,
    backrefs: bool = False,
    dedupe: bool = True,
) -> tuple[list[str], str]:
    """Ensure a line is present, replacing, inserting, and deduping.

    Ported from lineinfile_dedupe. Scans for regexp or search_string
    matches, literal occurrences of the line, and insertafter or
    insertbefore anchors, then inserts or replaces exactly one
    instance and, when dedupe is set, removes every other match.

    :param list[str] lines: Current file lines
    :param str line: The line that must be present
    :param Optional[str] regexp: Pattern matching lines to replace
    :param Optional[str] search_string: Literal text marking lines to
        replace; mutually exclusive with regexp
    :param Optional[str] insertafter: Pattern, 'EOF', or None
    :param Optional[str] insertbefore: Pattern, 'BOF', or None
    :param bool firstmatch: Anchor on the first match instead of the
        last
    :param bool backrefs: Expand regexp backreferences into the line
    :param bool dedupe: Remove duplicate matches beyond the kept one
    :returns tuple[list[str], str]: (new_lines, msg); msg is empty
        when nothing was added or replaced
    :raises ValueError: If patterns are invalid or no action applies
    """
    match_re, insert_re = compile_line_patterns(
        regexp, insertafter, insertbefore
    )

    new_lines = lines[:]

    line_indices: list[int] = []
    match_indices: list[int] = []
    relative_insert_indices: list[int] = []
    dedupe_indices: list[int] = []
    match_choice = 0 if firstmatch else -1
    insert_index: Optional[int] = None
    replace_index: Optional[int] = None
    keep_index: Optional[int] = None
    msg = ""

    for lineno, cur_line in enumerate(lines):
        if regexp:
            if match_re.search(cur_line):
                match_indices.append(lineno)
        elif search_string:
            if search_string in cur_line:
                match_indices.append(lineno)

        if line == cur_line:
            line_indices.append(lineno)

        if insert_re and insert_re.search(cur_line):
            relative_insert_indices.append(lineno)

    if not line_indices:
        if not match_indices:
            if not relative_insert_indices:
                if insertbefore == "BOF":
                    insert_index = 0
                else:
                    insert_index = len(new_lines)
            else:
                if insertafter:
                    insert_index = relative_insert_indices[match_choice] + 1
                elif insertbefore:
                    insert_index = relative_insert_indices[match_choice]
                else:
                    raise ValueError(
                        "'relative_insert_indices' should never be "
                        "populated if insertafter and insertbefore are "
                        "None"
                    )
        else:
            replace_index = match_indices[match_choice]
    else:
        if relative_insert_indices:
            if insertbefore:
                insertbefore_line_indices = [
                    i
                    for i in line_indices
                    if i < relative_insert_indices[match_choice]
                ]
                if len(insertbefore_line_indices) > 0:
                    # Keep instance closest to insertbefore match
                    keep_index = insertbefore_line_indices[-1]
                else:
                    insert_index = relative_insert_indices[match_choice]
            if insertafter:
                insertafter_line_indices = [
                    i
                    for i in line_indices
                    if i > relative_insert_indices[match_choice]
                ]
                if len(insertafter_line_indices) > 0:
                    # Keep instance closest to insertafter match
                    keep_index = insertafter_line_indices[0]
                else:
                    insert_index = relative_insert_indices[match_choice] + 1
        else:
            keep_index = line_indices[match_choice]

    if insert_index is not None:
        new_lines.insert(insert_index, line)
        keep_index = insert_index
        msg = "line added"

    elif replace_index is not None:
        match_line = lines[replace_index]
        if backrefs and regexp:
            match = match_re.search(match_line)
            expanded_line = match.expand(line) if match else line
        else:
            expanded_line = line

        new_lines[replace_index] = expanded_line
        keep_index = replace_index
        msg = "line replaced"

    else:
        if keep_index is None and not match_indices:
            raise ValueError("No lines found, added or replaced")

    if dedupe:
        # Index 0 is a valid keep or insert position, so these
        # comparisons test for None explicitly; the donor treated 0
        # as unset and deduped the wrong indices after a BOF insert
        for i in match_indices + line_indices:
            if (
                keep_index is not None
                and i > keep_index
                and insert_index is not None
            ):
                dedupe_indices.append(i + 1)
            elif i != keep_index:
                dedupe_indices.append(i)
        dedupe_count = len(dedupe_indices)
        for i in sorted(set(dedupe_indices), reverse=True):
            del new_lines[i]
        if dedupe_count:
            plural = "s" if dedupe_count != 1 else ""
            suffix = f"{dedupe_count} line{plural} deduped"
            msg = f"{msg} {suffix}" if msg else suffix

    return new_lines, msg


def remove_lines(
    lines: list[str],
    line: Optional[str] = None,
    regexp: Optional[str] = None,
    search_string: Optional[str] = None,
) -> tuple[list[str], int]:
    """Remove lines matching a pattern, literal line, or search text.

    Ported from lineinfile_dedupe unchanged.

    :param list[str] lines: Current file lines
    :param Optional[str] line: Exact line to remove
    :param Optional[str] regexp: Pattern matching lines to remove
    :param Optional[str] search_string: Literal text marking lines to
        remove
    :returns tuple[list[str], int]: (new_lines, removed_count)
    :raises ValueError: If regexp does not compile
    """
    match_re, _unused = compile_line_patterns(regexp, None, None)

    new_lines: list[str] = []
    removed_count = 0

    for cur_line in lines:
        if (
            regexp
            and match_re.search(cur_line)
            or search_string
            and search_string in cur_line
            or line
            and cur_line.rstrip("\r\n") == line
        ):
            removed_count += 1  # match is found, skip this line
        else:
            new_lines.append(cur_line)

    return new_lines, removed_count


def _find_marker_pairs(
    lines: list[str],
    begin_line: str,
    end_line: str,
) -> list[tuple[int, int]]:
    """Locate all begin and end marker pairs in the lines.

    :param list[str] lines: Current file lines
    :param str begin_line: The rendered begin marker line
    :param str end_line: The rendered end marker line
    :returns list[tuple[int, int]]: (begin, end) index pairs
    :raises ValueError: On an unpaired or misordered marker
    """
    pairs: list[tuple[int, int]] = []
    begin_index: Optional[int] = None

    for lineno, cur_line in enumerate(lines):
        if cur_line.strip() == begin_line.strip():
            if begin_index is not None:
                raise ValueError(
                    f"Nested or unclosed begin marker at line "
                    f"{begin_index + 1}"
                )
            begin_index = lineno
        elif cur_line.strip() == end_line.strip():
            if begin_index is None:
                raise ValueError(
                    f"End marker without begin marker at line {lineno + 1}"
                )
            pairs.append((begin_index, lineno))
            begin_index = None

    if begin_index is not None:
        raise ValueError(
            f"Begin marker without end marker at line {begin_index + 1}"
        )

    return pairs


def render_markers(
    marker: str,
    marker_begin: str,
    marker_end: str,
) -> tuple[str, str]:
    """Render the begin and end marker lines from the marker template.

    :param str marker: Marker template containing '{mark}'
    :param str marker_begin: Text substituted for the begin marker
    :param str marker_end: Text substituted for the end marker
    :returns tuple[str, str]: (begin_line, end_line)
    :raises ValueError: If the template lacks '{mark}' or renders both
        markers identically
    """
    if "{mark}" not in marker:
        raise ValueError("marker must contain '{mark}'")
    begin_line = marker.replace("{mark}", marker_begin)
    end_line = marker.replace("{mark}", marker_end)
    if begin_line == end_line:
        raise ValueError("begin and end markers must differ")
    return begin_line, end_line


def ensure_block(
    lines: list[str],
    block: str,
    marker: str = "# {mark} ANSIBLE MANAGED BLOCK",
    marker_begin: str = "BEGIN",
    marker_end: str = "END",
    insertafter: Optional[str] = None,
    insertbefore: Optional[str] = None,
) -> tuple[list[str], str]:
    """Ensure a marked block is present exactly once.

    The first marker pair found is replaced in place with the desired
    block; every further pair is removed, which is the line engine's
    deduplication philosophy applied to regions: one canonical
    instance survives at its anchor and drift collapses into it. When
    no pair exists, the block is inserted at the insertafter or
    insertbefore anchor, or appended at EOF.

    An empty block removes the managed block entirely.

    :param list[str] lines: Current file lines
    :param str block: Block content without markers; empty removes
    :param str marker: Marker template containing '{mark}'
    :param str marker_begin: Text substituted for the begin marker
    :param str marker_end: Text substituted for the end marker
    :param Optional[str] insertafter: Pattern, 'EOF', or None
    :param Optional[str] insertbefore: Pattern, 'BOF', or None
    :returns tuple[list[str], str]: (new_lines, msg)
    :raises ValueError: On invalid markers, patterns, or marker state
    """
    begin_line, end_line = render_markers(marker, marker_begin, marker_end)
    pairs = _find_marker_pairs(lines, begin_line, end_line)

    if not block:
        return remove_block(lines, marker, marker_begin, marker_end)

    block_lines = [begin_line] + block.splitlines() + [end_line]

    if pairs:
        first_begin, first_end = pairs[0]
        new_lines = lines[:first_begin] + block_lines + lines[first_end + 1 :]
        # Remove duplicate pairs, adjusting for the first replacement
        offset = len(block_lines) - (first_end - first_begin + 1)
        removed = 0
        for begin, end in pairs[1:]:
            start = begin + offset - removed
            stop = end + offset - removed + 1
            del new_lines[start:stop]
            removed += stop - start
        msg = "block replaced"
        if len(pairs) > 1:
            msg += f" ({len(pairs) - 1} duplicate blocks deduped)"
        return new_lines, msg

    _unused, insert_re = compile_line_patterns(None, insertafter, insertbefore)

    new_lines = lines[:]
    insert_index = len(new_lines)

    if insertbefore == "BOF":
        insert_index = 0
    elif insert_re:
        anchor_indices = [
            lineno
            for lineno, cur_line in enumerate(lines)
            if insert_re.search(cur_line)
        ]
        if anchor_indices:
            if insertafter:
                insert_index = anchor_indices[-1] + 1
            else:
                insert_index = anchor_indices[-1]

    new_lines[insert_index:insert_index] = block_lines
    return new_lines, "block added"


def remove_block(
    lines: list[str],
    marker: str = "# {mark} ANSIBLE MANAGED BLOCK",
    marker_begin: str = "BEGIN",
    marker_end: str = "END",
) -> tuple[list[str], str]:
    """Remove every managed block matching the marker pair.

    :param list[str] lines: Current file lines
    :param str marker: Marker template containing '{mark}'
    :param str marker_begin: Text substituted for the begin marker
    :param str marker_end: Text substituted for the end marker
    :returns tuple[list[str], str]: (new_lines, msg)
    :raises ValueError: On invalid markers or marker state
    """
    begin_line, end_line = render_markers(marker, marker_begin, marker_end)
    pairs = _find_marker_pairs(lines, begin_line, end_line)

    if not pairs:
        return lines[:], "no block found"

    new_lines = lines[:]
    for begin, end in reversed(pairs):
        del new_lines[begin : end + 1]

    count = len(pairs)
    plural = "s" if count != 1 else ""
    return new_lines, f"{count} block{plural} removed"


__all__ = [
    "compile_line_patterns",
    "ensure_block",
    "ensure_line",
    "remove_block",
    "remove_lines",
    "render_markers",
]
