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
- ``@reboot`` and its calendar siblings - are a Vixie cron form that
POSIX does not define, recognized here because the crons hosts
actually run are Vixie-descended and their files hold them: the read
side describes the host, the way getent is read without being POSIX.
They are a closed set and not a fallback - a line that is neither
blank, a comment, an assignment, nor a schedule and a command is a
line this does not understand, and it fails rather than being
dropped: a crontab quietly missing a job reads as a host that does
not run it.

Fields are kept as the file wrote them.  POSIX spells a field as a
number, a range, a comma list or ``*``; the ``*/5`` steps and the
``jan``/``mon`` names are Vixie's spellings on top of that; the ``~``
random ranges are OpenBSD's, written into its own stock root crontab;
``@every_minute`` and ``@every_second`` are FreeBSD's.  All of them
are published as a reader would find them in the file, because
rewriting any into another spelling would claim a file the host does
not have.  What they mean in wall-clock terms is a question for
whoever asks it, not an answer to store.

The parse is not routed through jc, and the reason is on record so
that nobody has to find it out again.  jc 1.25.7 ships ``crontab`` and
``crontab-u`` parsers, and every corpus in the unit suite was run
through both against this parser.  The three system-form corpora came
back identical.  The two per-user corpora did not, and the losses were
structural rather than cosmetic: jc pops every ``@`` line out and
appends them after the five-field rows in reverse file order, so
"jobs in the order the file wrote them" cannot be rebuilt from its
output without re-walking the raw lines - which is the parser; a
quoted assignment keeps its quotes, so ``MAILTO=""`` comes back as two
quote characters; nothing is refused, so a sentence of five words is
a schedule, a line with four fields puts its command in the weekday,
``@nosuch`` is a special string and a bare ``@reboot`` raises
IndexError; and a ``~``-leading OpenBSD line whose command carries an
``=`` is filed as a variable named ``~ 2 * * 6 FOO``.  What jc
contributes net of all that is a whitespace split, so the parse stays
here where the strictness is.

``anacron`` is deliberately not read here.  Its table is four fields -
a period, a delay, a job identifier and a command - with no user
column and no schedule in cron's sense, and its ``@monthly`` sits in
the period field rather than replacing a schedule.  It shares a
neighbourhood with cron and not a format, so reading it through this
would produce confident nonsense.

That is a boundary and not a gap.  ``anacron`` is cronie and Debian
territory, so a parser for it belongs to an OS collection, which can
answer in the row shape the ``schedule`` lookup already joins.
"""

from __future__ import annotations

import re

from typing import Any, Optional

from ansible_collections.o0_o.posix.plugins.module_utils.evidence_utils import (  # noqa: E501
    EVIDENCE,
    compose_evidence,
)

# A line that sets a variable for every job beneath it.  The name is
# anchored as an identifier, which is what tells an assignment from a
# job: no cron field can start with a letter and be followed by an
# equals sign, because a schedule's first field is a minute.
CRON_ASSIGNMENT = re.compile(
    r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=(?P<value>.*)$"
)

# The schedules cron names instead of spelling.  A form of its own
# rather than a fallback, so a line naming one is understood and a
# line naming something else is not.  The first eight are Vixie's and
# every supported platform takes them; the last two are FreeBSD's own,
# recognized because FreeBSD is a supported platform and its crontabs
# may hold them.
CRON_SPECIALS = (
    "reboot",
    "yearly",
    "annually",
    "monthly",
    "weekly",
    "daily",
    "midnight",
    "hourly",
    "every_minute",
    "every_second",
)
CRON_SPECIAL = re.compile(
    r"^@(?P<special>" + "|".join(CRON_SPECIALS) + r")(?:\s+(?P<rest>.*))?$"
)

# What a schedule field may be written with.  Digits and the
# punctuation cron gives them: a list, a range, a step, the star that
# means every one of them, and OpenBSD's ~ - a random value within a
# range, which stock OpenBSD writes into its own root crontab, so a
# parser refusing it fails a supported platform in factory state.
# The set is checked rather than the meaning, because a field naming
# an hour that does not exist is cron's complaint to make, while a
# command that landed in a field position is this parser's.
CRON_FIELD = re.compile(r"^[0-9A-Za-z*,/~-]+$")

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

# Where each implementation keeps the crontabs it was given.  Debian
# nests its own under /var/spool/cron, so the deeper path is tried
# first and the directory above it yields nothing, every entry in it
# being a directory rather than a crontab.
CRON_SPOOLS = (
    "/var/spool/cron/crontabs",
    "/var/spool/cron",
    "/var/cron/tabs",
    "/usr/lib/cron/tabs",
)

# What a host answers where there is no crontab to read, or no crontab
# command to read it with.  A user with no crontab has no crontab, and
# a host with no cron runs nothing on a schedule; neither is a fault,
# so the status rides back as an answer for the caller to read.
CRON_RCS = [0, 1, 2, 126, 127]

# What this module is called, which is what an entry names as having
# contributed it
FQCN = "o0_o.posix.cron"

# The command that answers for a crontab it was not given a file for
CRON_COMMANDS = ("crontab",)

# The one crontab every implementation keeps at the same place
SYSTEM_CRONTAB = "/etc/crontab"

# What a host answers where the crontab command is not there to run.
# A user with no crontab and a host with no crontab command are two
# different answers, and only the status tells them apart.
CRON_MISSING_RCS = (126, 127)

# What the fixed paths are asked about with.  A sweep that finds
# nothing cannot say whether there was nothing to find or nothing to
# look in, so each path a caller names rather than discovers is asked
# about directly - which is what lets an absence be filed as one.
CRON_FIXED_PATHS = ("/etc/crontab", "/etc/cron.d")

# What asks whether a path is there
CRON_EXISTS_COMMANDS = ("test",)

# What names the files a directory holds
CRON_LIST_COMMANDS = ("ls",)

# Where the drop-in crontabs live, each its own file with a user column
CRON_DROPIN_DIR = "/etc/cron.d"

# What reading a file is done with, here as everywhere
FILE_READ_COMMANDS = ("cat",)


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
    rc: int,
    output: str,
    e_prefix: str,
    user_column: bool = False,
) -> tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
    """Canonical COMMAND_SPEC parser for a crontab.

    A crontab that is not there prints nothing and exits non-zero,
    which is an answer of None rather than a fault: the caller reads
    the status to tell a user with no crontab from one whose crontab
    could not be read.

    :param int rc: The exit status, which the caller reads
    :param str output: Raw contents of the crontab
    :param str e_prefix: Error prefix for context
    :param bool user_column: Whether rows here name the user to run as
    :returns tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
        What the crontab configures, and the error a line it does not
        understand raises
    """
    del rc  # what was printed is parsed whatever the status

    if not (output or "").strip():
        return None, None

    try:
        return parse_crontab(output, user_column=user_column), None
    except ValueError as err:
        return None, [ValueError(f"{e_prefix}{err}")]


def _parse_exists(
    rc: int,
    output: str,
    e_prefix: str,
) -> tuple[Optional[bool], Optional[list[Exception]]]:
    """Canonical COMMAND_SPEC parser for an existence probe.

    ``test -e`` says one thing with its status and nothing with its
    output, so the status is the answer: there, or asked about and not
    there.

    :param int rc: The exit status, which is the answer
    :param str output: Raw stdout, which is empty
    :param str e_prefix: Error prefix for context
    :returns tuple[Optional[bool], Optional[list[Exception]]]: Whether
        the path is there, and never an error
    """
    del output, e_prefix  # the status is the whole of the answer

    return (rc == 0), None


def _parse_owner_uid(
    rc: int,
    output: str,
    e_prefix: str,
) -> tuple[Optional[int], Optional[list[Exception]]]:
    """Canonical COMMAND_SPEC parser for a crontab owner's uid.

    The same reading the effective uid gets, with the status ignored:
    a spool file naming somebody the host will not resolve leaves the
    crontab unfiled rather than failing the batch.

    :param int rc: The exit status, which is not read
    :param str output: Raw stdout of ``id -u``
    :param str e_prefix: Error prefix for context
    :returns tuple[Optional[int], Optional[list[Exception]]]: The uid,
        and whatever reading it raised
    """
    del rc  # a name the host will not resolve is not a fault

    from ansible_collections.o0_o.posix.plugins.module_utils.id_utils import (
        _parse_effective_uid,
    )

    return _parse_effective_uid(output, e_prefix)


def _parse_spool_names(
    rc: int,
    output: str,
    e_prefix: str,
) -> tuple[Optional[list[str]], Optional[list[Exception]]]:
    """Canonical COMMAND_SPEC parser for the spool sweep.

    Answers with the names of everyone holding a crontab, sorted and
    without repeats: two implementations' spools may both exist on one
    host and a user may appear in either.

    :param int rc: The exit status, which is not read
    :param str output: Raw stdout of the sweep
    :param str e_prefix: Error prefix for context
    :returns tuple[Optional[list[str]], Optional[list[Exception]]]: The
        names, and never an error
    """
    del rc, e_prefix  # a host with no spool to sweep is not a fault

    names = sorted(
        {
            line.strip()
            for line in (output or "").splitlines()
            if line.strip()
        }
    )

    return (names or None), None


def get_cron_survey_requests() -> list[dict[str, Any]]:
    """Build the batch that asks a host what it schedules.

    Four questions that need no answer from each other: what the
    system crontab says, which drop-in files exist, whose crontabs the
    spools hold, and what the running identity's own crontab is.

    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (  # noqa: E501
        CRON_COMMAND_SPEC,
    )
    from ansible_collections.o0_o.posix.plugins.module_utils.file_utils import (  # noqa: E501
        get_file_command_requests,
    )
    from ansible_collections.o0_o.posix.plugins.module_utils.id_utils import (
        get_effective_uid_command_requests,
    )

    from ansible_collections.o0_o.core.plugins.module_utils import (
        process_command_spec,
    )

    requests = get_file_command_requests([SYSTEM_CRONTAB])

    # Whether each fixed path is there at all, so that a path which is
    # not can be filed as absent rather than left unmentioned
    requests.extend(
        process_command_spec(
            CRON_COMMAND_SPEC,
            cmd_type="crontab_exists",
            path=list(CRON_FIXED_PATHS),
        )
    )

    for cmd_type in ("crontab_dropins", "crontab_spools", "crontab_self"):
        asked = process_command_spec(CRON_COMMAND_SPEC, cmd_type=cmd_type)
        if cmd_type == "crontab_self":
            # A crontab is what answers here, whatever shell read the
            # sweep back: the two sweeps are scripts and name the
            # commands they are, and this one is the crontab itself
            for request in asked:
                request[EVIDENCE] = list(CRON_COMMANDS)
        requests.extend(asked)

    return requests + get_effective_uid_command_requests()


def get_cron_read_requests(
    dropins: list[str],
    spools: list[str],
    holders: list[str],
) -> list[dict[str, Any]]:
    """Build the batch that reads what the survey named.

    Nothing here could have ridden the survey: every path and every
    name in it is something the survey had to answer with first.

    :param list[str] dropins: The drop-in files the sweep named
    :param list[str] spools: The spool files to read
    :param list[str] holders: The users whose uid to ask for
    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (  # noqa: E501
        CRON_COMMAND_SPEC,
    )
    from ansible_collections.o0_o.posix.plugins.module_utils.file_utils import (  # noqa: E501
        get_file_command_requests,
    )

    from ansible_collections.o0_o.core.plugins.module_utils import (
        process_command_spec,
    )

    requests: list[dict[str, Any]] = []

    if dropins or spools:
        requests.extend(
            get_file_command_requests(sorted(dropins) + sorted(spools))
        )

    if holders:
        requests.extend(
            process_command_spec(
                CRON_COMMAND_SPEC,
                cmd_type="crontab_owner",
                user=sorted(holders),
            )
        )

    return requests


def cron_survey_answers(
    cmds_completed: list[dict[str, Any]],
) -> dict[str, Any]:
    """Read a cron survey's batch into what it settled and what it named.

    One reading, because both producers of these facts read the same
    batch the same way: the module that asks on its own and the gather
    that asks beside everything else.

    :param list[dict[str, Any]] cmds_completed: Command results
    :returns dict[str, Any]: The files it read keyed by path, the user
        views it settled keyed by stringified uid, the drop-in paths
        and crontab holders it named, and the errors a crontab it
        could not read raised
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.file_utils import (  # noqa: E501
        process_file_command_results,
    )
    from ansible_collections.o0_o.posix.plugins.module_utils.id_utils import (
        process_effective_uid_results,
    )

    from ansible_collections.o0_o.core.plugins.module_utils import (
        process_all_command_results,
    )

    processed = process_all_command_results(cmds_completed)
    errors: list[Exception] = []

    def named(cmd_type: str) -> list[str]:
        answered = processed.get(cmd_type) or {}
        if not isinstance(answered, dict):
            return []
        return list(answered.get("parsed") or [])

    # Only the file this asked for.  A gather batches every subset's
    # reads together, so the results carry /etc/passwd and /etc/fstab
    # among them, and a crontab parser handed a passwd file would
    # report every line of it as one it does not understand
    files = {
        path: answered
        for path, answered in process_file_command_results(
            cmds_completed
        ).items()
        if path == SYSTEM_CRONTAB
    }

    for path, answered in files.items():
        content = answered.get("parsed")
        if content is None:
            continue
        try:
            answered["config"] = parse_crontab(content, user_column=True)
        except ValueError as err:
            errors.append(ValueError(f"{path}: {err}"))

    # What each fixed path answered about its own existence, which is
    # what tells a path that is not there from one that would not be
    # read
    there: dict[str, bool] = {}
    probes = processed.get("crontab_exists")
    if isinstance(probes, dict):
        probes = [probes]
    for probe in probes or []:
        if not isinstance(probe, dict):
            continue
        path = (probe.get("args") or {}).get("path")
        if path is not None and isinstance(probe.get("parsed"), bool):
            there[path] = probe["parsed"]

    views: dict[str, dict[str, Any]] = {}
    own = processed.get("crontab_self")
    uid = process_effective_uid_results(cmds_completed)

    if uid is not None and isinstance(own, dict):
        view: dict[str, Any] = {
            EVIDENCE: compose_evidence(commands=CRON_COMMANDS)
        }
        # A host with no crontab command was never able to answer the
        # question, which is not the same as answering that there is
        # no crontab.  The key is left off - the store's word for
        # never asked - and the record still names what was attempted.
        # The status is read off the raw result, the processed one
        # carrying what was parsed rather than how it exited
        asked = [
            result
            for result in cmds_completed
            if isinstance(result, dict)
            and result.get("type") == "crontab_self"
        ]
        unaskable = any(
            result.get("rc") in CRON_MISSING_RCS for result in asked
        )

        if not unaskable:
            view["crontab"] = own.get("parsed")
        views[str(uid)] = view

        for err in own.get("errors") or []:
            errors.append(err)

    return {
        "files": files,
        "views": views,
        "there": there,
        "dropins": named("crontab_dropins"),
        "holders": named("crontab_spools"),
        "errors": errors,
    }


def spool_paths(holders: list[str]) -> list[str]:
    """Every path a named user's crontab could be sitting at.

    The sweep answers with names, because a name is what identifies
    the user; which spool it was found in is rebuilt here rather than
    carried, so one candidate per implementation is read and the ones
    that are not there answer as absent.

    :param list[str] holders: The users holding a crontab
    :returns list[str]: The spool files to read
    """
    return [
        f"{spool}/{name}"
        for name in sorted(holders)
        for spool in CRON_SPOOLS
    ]


def compose_cron_holdings(
    answers: dict[str, Any],
    cmds_completed: list[dict[str, Any]],
) -> dict[str, Any]:
    """Read the batch that read what the survey named.

    The drop-in files join the ones the survey read, and each spool
    file is filed under the uid the host said owns it - asked with
    ``id``, so that nothing here depends on a passwd file this has not
    read.

    :param dict[str, Any] answers: What the survey settled and named
    :param list[dict[str, Any]] cmds_completed: The read batch's
        results
    :returns dict[str, Any]: The files, the user views and the errors
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.file_utils import (  # noqa: E501
        process_file_command_results,
    )

    from ansible_collections.o0_o.core.plugins.module_utils import (
        process_all_command_results,
    )

    files = dict(answers["files"])
    views = dict(answers["views"])
    errors = list(answers["errors"])
    spools = set(spool_paths(answers["holders"]))

    # The same discipline as the survey: only what this asked for
    wanted = set(answers["dropins"]) | spools

    for path, answered in process_file_command_results(
        cmds_completed
    ).items():
        if path not in wanted:
            continue

        content = answered.get("parsed")
        if content is None:
            continue
        try:
            answered["config"] = parse_crontab(
                content, user_column=path not in spools
            )
        except ValueError as err:
            errors.append(ValueError(f"{path}: {err}"))
            continue
        files[path] = answered

    processed = process_all_command_results(cmds_completed)
    owners = processed.get("crontab_owner")
    if isinstance(owners, dict):
        owners = [owners]

    uids: dict[str, int] = {}
    for owner in owners or []:
        if not isinstance(owner, dict):
            continue
        name = (owner.get("args") or {}).get("user")
        parsed = owner.get("parsed")
        if name and isinstance(parsed, int):
            uids[name] = parsed

    for path in sorted(spools):
        config = (files.get(path) or {}).get("config")
        if config is None:
            continue

        uid = uids.get(path.rsplit("/", 1)[-1])
        if uid is None:
            continue

        views[str(uid)] = {
            "crontab": config,
            EVIDENCE: compose_evidence(
                files=[path], commands=FILE_READ_COMMANDS
            ),
        }

    return {
        "files": files,
        "views": views,
        "there": answers.get("there") or {},
        "errors": errors,
    }


def compose_cron_paths(
    files: dict[str, Any],
    dropins: list[str],
    there: Optional[dict[str, bool]] = None,
) -> dict[str, Any]:
    """Compose the crontab entries of the o0_paths store.

    A crontab is a file, so what it configures is a fact about that
    file: the bytes under ``content`` and what they schedule under
    ``config``, the way /etc/fstab carries the filesystems it names.

    Three states, because a path answers three ways and the store has
    a word for each.  A path that is not there is ``null`` - asked
    about and absent.  A path that is there and was read carries what
    it says.  A path that is there and would not be read carries an
    entry naming what was consulted and nothing else, which is the
    truthful statement that it exists and nothing was learned about
    it - the same entry the compliance sweep leaves for the shell it
    ran the probes with.

    Telling the first from the third is what the existence probe is
    for.  A ``cat`` that failed cannot say whether the file is missing
    or unreadable, which is why this used to leave both unmentioned
    and a host with no cron published no trace of the fact.

    ``/etc/cron.d`` is filed as the directory it is: its ``config`` is
    the drop-in files it holds, the way ``/etc/shells`` carries the
    shells it names, so a directory that is there and empty is a list
    with nothing in it and a directory that is not there is null.

    Only the files whose rows carry a user column land here. A spool
    file is a crontab too, and it is read, but what it says is a fact
    about the user who owns it rather than about a path a play would
    ever name.

    :param dict[str, Any] files: What the reads answered, keyed by path
    :param list[str] dropins: The drop-in files the sweep named
    :param Optional[dict[str, bool]] there: Whether each fixed path is
        there, as the existence probes answered
    :returns dict[str, Any]: The crontab entries, keyed by path
    """
    entries: dict[str, Any] = {}
    exists = there or {}

    for path in [SYSTEM_CRONTAB] + sorted(dropins):
        answered = files.get(path) or {}
        content = answered.get("parsed")
        config = answered.get("config")

        if content is not None and config is not None:
            entries[path] = {
                "content": content,
                "config": config,
                EVIDENCE: compose_evidence(commands=FILE_READ_COMMANDS),
            }
            continue

        if exists.get(path) is False:
            entries[path] = None
            continue

        if path in exists:
            # There, and nothing learned about it. A refused read is
            # not an absence and saying nothing at all would read as
            # one
            entries[path] = {
                EVIDENCE: compose_evidence(
                    commands=sorted(
                        {*FILE_READ_COMMANDS, *CRON_EXISTS_COMMANDS}
                    )
                ),
            }

    if CRON_DROPIN_DIR in exists:
        entries[CRON_DROPIN_DIR] = (
            {
                "config": sorted(dropins),
                EVIDENCE: compose_evidence(
                    commands=sorted(
                        {*CRON_LIST_COMMANDS, *CRON_EXISTS_COMMANDS}
                    )
                ),
            }
            if exists[CRON_DROPIN_DIR]
            else None
        )

    return entries


def compose_cron_users(
    views: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Compose the crontab each user holds, keyed by uid.

    A crontab is a fact about the user it runs as, and the only key
    this collection files a user under is their uid.  A user asked
    about and holding none carries a null, which is the store's word
    for asked and not there; a user nobody asked about is absent.

    :param dict[str, dict[str, Any]] views: What each uid's crontab
        says and what was consulted for it, keyed by stringified uid
    :returns dict[str, Any]: The o0_users entries
    """
    entries: dict[str, Any] = {}

    for uid, view in sorted(views.items()):
        entry: dict[str, Any] = {"uid": int(uid)}
        # A question that could not be put is not a question answered
        # in the negative, so the key is there only where something
        # asked it
        if "crontab" in view:
            entry["crontab"] = view["crontab"]
        entry[EVIDENCE] = view[EVIDENCE]
        entries[uid] = entry

    return entries


__all__ = [
    "CRON_ASSIGNMENT",
    "CRON_COMMANDS",
    "CRON_RCS",
    "CRON_DROPIN_DIR",
    "CRON_FIXED_PATHS",
    "CRON_MISSING_RCS",
    "CRON_SPOOLS",
    "CRON_FIELD",
    "CRON_FIELDS",
    "CRON_MONTHS",
    "CRON_WEEKDAYS",
    "CRON_SPECIAL",
    "CRON_SPECIALS",
    "FQCN",
    "SYSTEM_CRONTAB",
    "compose_cron_holdings",
    "compose_cron_paths",
    "cron_survey_answers",
    "compose_cron_users",
    "get_cron_read_requests",
    "get_cron_survey_requests",
    "spool_paths",
    "parse_crontab",
]
