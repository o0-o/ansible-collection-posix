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

"""What a host is configured to run on a schedule.

A crontab is two kinds of line that share a file.  Some set an
environment variable for every job below them, and some are jobs.
Both are configuration and neither is the other, so a parsed crontab
says which it is holding rather than flattening the two into a list of
strings.

The rows differ by where the file lives.  A system crontab and the
files under ``/etc/cron.d`` carry a user column - they are root's
statement about what runs as whom - and a per-user crontab does not,
because the spool it sits in already answers that.  Nothing here
guesses which it is reading: the caller knows which file it asked for
and says so.

A schedule is five fields or one special string.  The special strings
are a form cron defines - ``@reboot`` and its calendar siblings - and
not a fallback for a line that would not parse.  A line that is
neither blank, a comment, an assignment, nor a schedule and a command
is a line this does not understand, and it fails rather than being
dropped: a crontab quietly missing a job reads as a host that does not
run it.

Fields are kept as the file wrote them.  ``*/5``, ``1-5``, ``1,15``,
``jan,feb`` and ``mon`` are all cron's own spellings of a schedule and
none of them is more canonical than another, so what is published is
what a reader would find in the file.  What they mean in wall-clock
terms is a question for whoever asks it, not an answer to store.

``anacron`` is deliberately not read here.  Its table is four fields -
a period, a delay, a job identifier and a command - with no user
column and no schedule in cron's sense, and its ``@monthly`` sits in
the period field rather than replacing a schedule.  It shares a
neighbourhood with cron and not a format, so reading it through this
would produce confident nonsense.
"""

from __future__ import annotations

import re

from typing import Any, Optional

# A line that sets a variable for every job beneath it.  The name is
# anchored as an identifier, which is what tells an assignment from a
# job: no cron field can start with a letter and be followed by an
# equals sign, because a schedule's first field is a minute.
CRON_ASSIGNMENT = re.compile(
    r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=(?P<value>.*)$"
)

# The schedules cron names instead of spelling.  A form of its own
# rather than a fallback, so a line naming one is understood and a
# line naming something else is not.
CRON_SPECIALS = (
    "reboot",
    "yearly",
    "annually",
    "monthly",
    "weekly",
    "daily",
    "midnight",
    "hourly",
)
CRON_SPECIAL = re.compile(
    r"^@(?P<special>" + "|".join(CRON_SPECIALS) + r")(?:\s+(?P<rest>.*))?$"
)

# What a schedule field may be written with.  Digits and the
# punctuation cron gives them: a list, a range, a step, and the star
# that means every one of them.  The set is checked rather than the
# meaning, because a field naming an hour that does not exist is
# cron's complaint to make, while a command that landed in a field
# position is this parser's.
CRON_FIELD = re.compile(r"^[0-9A-Za-z*,/-]+$")

# Any run of letters in a field, which is only ever a month or a day
# spelled out
CRON_WORD = re.compile(r"[A-Za-z]+")

# The names cron takes, and the only two fields that take them. A
# minute is never called anything, so letters in the first three
# fields are a command that landed where a schedule belongs - which is
# what tells "not a crontab line at all" from a schedule, five words
# being five words either way.
CRON_MONTHS = (
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "oct",
    "nov",
    "dec",
)
CRON_WEEKDAYS = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")

# How many fields a schedule is written in, and what each of them may
# be named with
CRON_FIELDS = ("minute", "hour", "day", "month", "weekday")
CRON_FIELD_NAMES: tuple[tuple[str, ...], ...] = (
    (),
    (),
    (),
    CRON_MONTHS,
    CRON_WEEKDAYS,
)

# What this module is called, which is what an entry names as having
# contributed it
FQCN = "o0_o.posix.cron"


def _unquoted(value: str) -> str:
    """Strip one matching pair of quotes, the way cron does.

    An assignment may be quoted to keep whitespace cron would
    otherwise trim, so the quotes are the syntax and what is inside
    them is the value a job will see.

    :param str value: The text after the equals sign
    :returns str: The value cron would export
    """
    text = value.strip()

    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]

    return text


def _named_field(value: str, names: tuple[str, ...]) -> bool:
    """Whether one schedule field is written the way cron writes them.

    :param str value: The field as the file wrote it
    :param tuple[str, ...] names: The words this field may be spelled
        with, empty where it may only be counted
    :returns bool: True where cron would read it as a field
    """
    if not CRON_FIELD.match(value):
        return False

    return all(
        word.lower() in names for word in CRON_WORD.findall(value)
    )


def _parse_job(
    line: str,
    user_column: bool,
) -> Optional[dict[str, Any]]:
    """Read one job line, or answer None where it is not one.

    :param str line: The line as the file wrote it
    :param bool user_column: Whether rows here name the user to run as
    :returns Optional[dict[str, Any]]: The job, or None
    """
    found = CRON_SPECIAL.match(line)
    if found is not None:
        rest = (found.group("rest") or "").strip()
        if not rest:
            return None

        job: dict[str, Any] = {"schedule": {"special": found.group("special")}}
        if user_column:
            parts = rest.split(None, 1)
            if len(parts) != 2:
                return None
            job["user"], rest = parts[0], parts[1].strip()
        job["command"] = rest

        return job

    wanted = len(CRON_FIELDS) + (1 if user_column else 0)
    parts = line.split(None, wanted)

    if len(parts) != wanted + 1:
        return None

    fields = parts[: len(CRON_FIELDS)]
    if not all(
        _named_field(field, names)
        for field, names in zip(fields, CRON_FIELD_NAMES)
    ):
        return None

    job = {"schedule": dict(zip(CRON_FIELDS, fields))}
    if user_column:
        job["user"] = parts[len(CRON_FIELDS)]
    job["command"] = parts[-1].strip()

    return job if job["command"] else None


def parse_crontab(
    text: str,
    user_column: bool = False,
) -> dict[str, Any]:
    """Read a crontab into the two kinds of line it holds.

    :param str text: The file's contents
    :param bool user_column: Whether rows here name the user to run as,
        which the system crontab and the files under /etc/cron.d do and
        a per-user crontab does not
    :returns dict[str, Any]: The environment it sets and the jobs it
        runs, in the order the file wrote them
    :raises ValueError: If a line is none of the forms a crontab holds
    """
    environment: dict[str, str] = {}
    jobs: list[dict[str, Any]] = []

    for number, line in enumerate((text or "").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        job = _parse_job(line.strip(), user_column)
        if job is not None:
            jobs.append(job)
            continue

        found = CRON_ASSIGNMENT.match(line.strip())
        if found is not None:
            environment[found.group("name")] = _unquoted(found.group("value"))
            continue

        raise ValueError(
            f"line {number} is neither a comment, an assignment nor a"
            f" job: {line!r}"
        )

    return {"environment": environment, "jobs": jobs}


def _parse_crontab_file(
    output: str,
    e_prefix: str,
    user_column: bool = False,
) -> tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
    """Canonical COMMAND_SPEC parser for a crontab.

    :param str output: Raw contents of the file
    :param str e_prefix: Error prefix for context
    :param bool user_column: Whether rows here name the user to run as
    :returns tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
        What the crontab configures, and the error a line it does not
        understand raises
    """
    try:
        return parse_crontab(output, user_column=user_column), None
    except ValueError as err:
        return None, [ValueError(f"{e_prefix}{err}")]


__all__ = [
    "CRON_ASSIGNMENT",
    "CRON_FIELD",
    "CRON_FIELDS",
    "CRON_MONTHS",
    "CRON_WEEKDAYS",
    "CRON_SPECIAL",
    "CRON_SPECIALS",
    "FQCN",
    "parse_crontab",
]
