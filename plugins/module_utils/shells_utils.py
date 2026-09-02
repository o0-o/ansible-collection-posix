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

"""The login shells a host names, and what running one does.

``parse_shells`` reads ``/etc/shells``, which is a list of paths a
host is willing to call a login shell.  That is a claim about
configuration, and it is all the file can be: a shell's configuration
is code, and the only honest way to know what that code does is to
run it and watch.

So the observation is a second thing, keyed by the pair that decides
it.  What a login shell hands you depends on which shell it is and
whose home it reads, and neither alone determines the answer: two
users sharing a shell get whatever their own dot files make, and one
user's two shells read two different sets of files.  The pair is the
key, and ``o0_shells[<shell>][<home>].config`` is what was observed
there - the environment, the mask and the locale that combination
actually produced.

The probe is ``env HOME=<home> <shell> -l -c <script>``.  ``env`` is
POSIX and takes its assignments as arguments rather than as shell
syntax, so a home with a space or a quote in it reaches the shell
whole.  ``-l`` is what makes the shell read the login files, which is
the whole point of asking.

A probe of the system layer rather than of a user uses
``HOME=/dev/null``.  Every POSIX host has ``/dev/null`` and none of
them has it as a directory, so ``~/.profile`` fails to resolve
identically everywhere, and the row is keyed by the literal path
probed rather than by a name invented for it.

Nothing probes every shell a host names.  A probe is a shell run, and
running every shell in ``/etc/shells`` on the chance someone logs in
with one is a cost with no answer attached.  What is probed is what a
producer was asked about, and the rest keep their keys with nothing
under them: the key says the host names this shell, and the empty
value says nothing has been observed of it.
"""

from __future__ import annotations

import posixpath
import re

from typing import Any, Iterable, Optional, Sequence, Union

from ansible_collections.o0_o.core.plugins.module_utils import (
    process_all_command_results,
    process_command_spec,
)

from ansible_collections.o0_o.posix.plugins.module_utils.command_utils import (
    format_command,
)

from ansible_collections.o0_o.core.plugins.module_utils.evidence_utils import (  # noqa: E501
    EVIDENCE,
    command_names,
    compose_evidence,
    merge_evidence,
)
from ansible_collections.o0_o.posix.plugins.module_utils.filter_utils import (
    decode_declared_content,
)
from ansible_collections.o0_o.posix.plugins.module_utils.locale_utils import (
    _parse_locale,
)
from ansible_collections.o0_o.posix.plugins.module_utils.path_utils import (
    canonicalize,
)
from ansible_collections.o0_o.utils.plugins.module_utils import strip_comments

# The home a probe of the system layer uses.  Documented, canonical,
# and present on every POSIX host without ever being a directory.
SHELL_SYSTEM_HOME = "/dev/null"

# The shell a producer probes when it was not told which
SHELL_DEFAULT = "/bin/sh"

# What a shell's environment says about the shell rather than about
# whoever ran it.  POSIX names every one of these and none of them is
# an identity: LANG and LC_CTYPE are the locale the login files set,
# PATH is where the shell will look for a command, TERM is the
# terminal type the session carries, and TZ and NLSPATH are the other
# two POSIX variables a login file plausibly sets that name no user.
#
# IFS is here for the opposite reason to the rest.  It is almost never
# exported, so on a healthy host its answer is null; a value is itself
# the finding, because an exported and modified IFS breaks word
# splitting for everything that host runs.  OPTIND stays out: it is
# getopts iteration state, always 1 in a fresh login, bookkeeping
# rather than configuration.
#
# Every name here is answered on every row that was probed - a value
# where the shell exported one, null where it did not - because ``env``
# prints the whole exported environment and so the answer is known
# either way.  That also makes a row say which questions were put to
# it: a key that is there was asked about, and a key that is not
# belongs to a gather taken before the name was on this list.
#
# Narrower than the environment ``o0_users`` publishes, deliberately.
# That fact is about a user and HOME, LOGNAME, MAIL, PWD and USER
# belong in it; this one is about a shell, and the same variables
# would only say which identity happened to run the probe.
SHELL_ENV_VARS = (
    "IFS",
    "LANG",
    "LC_CTYPE",
    "NLSPATH",
    "PATH",
    "TERM",
    "TZ",
)

# Where the parser leaves what a probe said about its own placement.
# A probe run through a login su is not told which shell to run - it
# runs the user's own - so the answer is what says where the row
# belongs.  The filer reads this and removes it; it never reaches a
# fact, which is why it is spelled as a private key rather than a
# field.
SHELL_FILING = "_filing"

# The variable a row is filed by rather than published with.  A row
# belongs to the shell that produced it, and the shell's own path is
# the key it is filed under, so publishing the same answer inside the
# row would be a constant echo of the key it chose.
SHELL_ENV_FILING = "SHELL"

# What the login probe asks the shell.  The shell itself is named
# beside these, because a probe of what a shell's own configuration
# does is a question about the shell: here the interpreter IS the
# subject, so it is evidence and not merely the thing that read the
# script.
SHELL_PROBE_QUESTIONS = ("alias", "env", "locale", "umask")

# What the probe prints between the three things it asks for, and
# after the last of them.  A login shell may print anything it likes
# before the first marker - a dot file that echoes is still a dot file
# that ran - so the first marker is where the answer starts, and the
# last is how the parser knows the script reached its end.
SHELL_UMASK_MARKER = "@UMASK@"
SHELL_ENV_MARKER = "@ENV@"
SHELL_LOCALE_MARKER = "@LOCALE@"
SHELL_ALIAS_MARKER = "@ALIAS@"
SHELL_END_MARKER = "@END@"

# Every exit status the probe reads as an answer rather than a fault.
# 126 and 127 are the shell's for a shell that cannot be run and one
# that is not there, and both mean the same thing to the fact: no row.
SHELL_RCS = [0, 126, 127]

# What a variable may be named, which is how a continuation line is
# told from the start of the next variable
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# What an alias may be named.  Wider than a variable name, because the
# standard allows the portable filename characters and four more, so
# ll., grep-i and %% are all names a host may really have used
_ALIAS_NAME = re.compile(r"[A-Za-z0-9._!%,@+:^-]+")


def _coerce_to_text(data: Union[str, Sequence[str]]) -> str:
    """Convert sequence or string input to text."""
    if isinstance(data, str):
        return data

    if isinstance(data, Iterable):
        return "\n".join(str(part) for part in data)

    return ""


def parse_shells(data: Union[str, Sequence[str], dict[str, Any]]) -> list[str]:
    """Parse /etc/shells style content into a list of shell paths.

    Accepts raw strings, iterable line collections, or dictionaries that
    look like results from Ansible's slurp/command modules.

    :param data: Raw content or structured command/slurp result.
    :returns: List of shell paths (without comments or blank lines).
    """
    text = ""

    if isinstance(data, dict):
        content = data.get("content")
        stdout = data.get("stdout")

        if isinstance(content, str):
            # A read or slurp result declares an encoded content. Only
            # a declaration justifies decoding: shell paths are
            # themselves base64 alphabet, so /bin/sh and /bin/bash
            # together decode without complaint into five junk bytes
            declared = decode_declared_content(content, data.get("encoding"))
            text = content if declared is None else declared
        elif isinstance(stdout, str):
            text = stdout
        else:
            # Attempt to treat dict values as sequence of lines
            text = _coerce_to_text(data.values())
    else:
        text = _coerce_to_text(data)

    if not text:
        return []

    cleaned = strip_comments(text)
    if not cleaned:
        return []

    shells = []
    for line in cleaned.splitlines():
        entry = line.strip()
        if entry:
            shells.append(entry)

    return shells


def _parse_env_block(
    text: str,
    keep: Sequence[str],
    complete: bool = False,
) -> dict[str, Optional[str]]:
    """Read an ``env`` block into the variables it printed.

    A value may hold newlines, and ``env`` prints them as newlines, so
    a line that does not begin with a variable name and an equals sign
    continues the value before it rather than starting a new one.

    Only the variables the caller names are kept.  A shell's
    environment is a place secrets live, and an observation is not a
    reason to copy them into a fact - which is why the caller says
    what it is observing rather than taking what it is handed.

    Asked for a complete answer, every name the caller named is
    published: its value where the shell exported one and null where
    the block confirmed it did not.  ``env`` prints the whole exported
    environment, so a name missing from a block that printed anything
    is a name the shell did not export - which is knowledge, and the
    store's word for it is null.

    A block that printed nothing is the other thing entirely.  A login
    shell always exports something, so an empty block is a probe that
    did not answer, and nothing is known: it yields no variables at
    all rather than a row of nulls claiming every one was checked.

    :param str text: The block between the env and locale markers
    :param Sequence[str] keep: The variables worth keeping, in the
        order a fact publishes them
    :param bool complete: Whether to answer for every name asked
        about rather than only the ones that were set
    :returns dict[str, Optional[str]]: The variables the shell had
        set, and where complete, nulls for the ones it had not
    """
    values: dict[str, str] = {}
    current: Optional[str] = None

    for line in text.splitlines():
        name, sep, value = line.partition("=")
        if sep and _ENV_NAME.fullmatch(name):
            current = name
            values[name] = value
        elif current is not None:
            values[current] += "\n" + line

    if complete:
        return {name: values.get(name) for name in keep} if values else {}

    return {name: values[name] for name in keep if name in values}


def _parse_alias_block(text: str) -> dict[str, str]:
    """Read an ``alias`` block into the aliases the shell had set.

    ``alias`` with no operands lists every alias, and what it prints
    is unspecified beyond being re-inputtable, so both spellings are
    read: bash prints ``alias ls='ls --color=auto'`` and dash prints
    ``ls='ls --color=auto'``.  A value may hold newlines, so a line
    that does not begin with a name and an equals sign continues the
    value before it, the way an ``env`` block's does.

    The quoting is the shell's own and is removed, because what the
    alias expands to is the fact and the quotes are how the shell
    said it.

    :param str text: The block between the alias and end markers
    :returns dict[str, str]: The aliases the shell had set
    """
    values: dict[str, str] = {}
    order: list[str] = []
    current: Optional[str] = None

    for line in text.splitlines():
        entry = line
        if current is None or not entry.startswith((" ", "\t")):
            stripped = entry.strip()
            if stripped.startswith("alias "):
                stripped = stripped[len("alias ") :]
            name, sep, value = stripped.partition("=")
            if sep and _ALIAS_NAME.fullmatch(name):
                current = name
                if name not in values:
                    order.append(name)
                values[name] = value
                continue
        if current is not None:
            values[current] += "\n" + entry

    aliases: dict[str, str] = {}
    for name in order:
        value = values[name]
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        aliases[name] = value

    return aliases


def _parse_shell_config(
    rc: int,
    output: str,
    e_prefix: str,
) -> tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
    """Canonical COMMAND_SPEC parser for one shell-context probe.

    Answers with what the combination produced - its ``env``, its
    ``umask`` and its ``locale`` - or with None where the shell did
    not run, which is what a shell that is not installed and one that
    cannot be executed both look like.

    A field the shell would not answer is left out rather than nulled:
    a host with no ``locale`` utility has a shell configuration with
    no locale in it, which is a different claim from a locale that is
    unset.

    :param int rc: The exit status the probe answered with
    :param str output: Raw stdout of the probe
    :param str e_prefix: Error prefix for context
    :returns tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
        What was observed of the combination, and never an error
    """
    del e_prefix  # a shell that is not there is not a fault

    text = output or ""
    if rc != 0 or SHELL_UMASK_MARKER not in text:
        return None, None

    _before, _marker, rest = text.partition(SHELL_UMASK_MARKER)
    umask_text, _marker, rest = rest.partition(SHELL_ENV_MARKER)
    env_text, _marker, rest = rest.partition(SHELL_LOCALE_MARKER)
    locale_text, _marker, rest = rest.partition(SHELL_ALIAS_MARKER)
    alias_text, _marker, _after = rest.partition(SHELL_END_MARKER)

    # A probe that stopped before the alias marker leaves the end
    # marker in the locale block, so the locale is trimmed to its own
    # end wherever the alias section turned out not to be there
    locale_text, _marker, _after = locale_text.partition(SHELL_END_MARKER)

    config: dict[str, Any] = {}

    # What the probe said about its own placement, for the filer. A
    # login su runs the user's own shell out of their own home and is
    # not told either, so the answer is the only thing that knows.
    placement = _parse_env_block(env_text, (SHELL_ENV_FILING, "HOME"))
    if placement:
        config[SHELL_FILING] = placement

    from ansible_collections.o0_o.posix.plugins.module_utils.limits_utils import (  # noqa: E501
        _parse_umask,
    )

    umask, _errors = _parse_umask(umask_text, "")
    if umask is not None:
        config["umask"] = umask

    # What the shell set, and nothing about who ran it. The identity
    # variables a login environment carries - HOME, LOGNAME, MAIL,
    # PWD, USER - describe whoever the probe turned out to be rather
    # than the shell being asked, and the home this row is filed under
    # is the key it is filed under
    env = _parse_env_block(env_text, SHELL_ENV_VARS, complete=True)
    if env:
        config["env"] = env

    locale, _errors = _parse_locale(locale_text, "")
    if locale:
        config["locale"] = locale

    aliases = _parse_alias_block(alias_text)
    if aliases:
        config["aliases"] = aliases

    return (config or None), None


def _named(request: dict[str, Any], subject: str) -> dict[str, Any]:
    """Name what a shell probe asks, the shell among it.

    The probe is a script, so argv names whatever read the script back
    - env(1), or the su that dropped identity first - and none of that
    is the question.  What was asked is the shell, which is the
    subject when the question is what a shell's own configuration
    does, and the things the script puts to it.

    :param dict[str, Any] request: The request to name, edited in
        place
    :param str subject: The shell being asked about, as a path or a
        bare name
    :returns dict[str, Any]: The request
    """
    request[EVIDENCE] = sorted(
        {posixpath.basename(subject), *SHELL_PROBE_QUESTIONS}
    )

    return request


def get_shell_login_requests(
    users: Iterable[str],
) -> list[dict[str, Any]]:
    """Build probes of each named user's own login shell.

    ``su`` with a login flag resets the environment to what the user
    really gets, which is why the probe is worth the drop: run bare
    under ``sudo`` it would report sudo's environment and call it the
    shell's.  It is not told which shell to run - the user's passwd
    entry decides - so the answer says which shell and which home it
    turned out to be, and the row is filed by that.

    Only root can drop.  ``su`` asks everybody else for a password on
    a terminal a probe does not have, so a caller that is not root
    passes no users here and asks bare instead.

    :param Iterable[str] users: The users whose own login shells are
        worth observing
    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (  # noqa: E501
        SHELL_COMMAND_SPEC,
    )

    requests = []
    for user in users:
        asked = process_command_spec(
            SHELL_COMMAND_SPEC,
            cmd_type="shell_login",
            user=user,
        )
        for request in asked:
            # No shell is named here, because none was asked for: the
            # user's passwd entry decides which one runs and the
            # answer says which it was, so the filer names it on the
            # row it files. su is a command the probe execs to get
            # there, so it is named as one
            request[EVIDENCE] = sorted({*SHELL_PROBE_QUESTIONS, "su"})
        requests.extend(asked)

    return requests


def get_shell_command_requests(
    pairs: Iterable[tuple[str, str]],
    dropper: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Build command requests for the combinations named.

    One request per pair, and only for the pairs a caller asked
    about.  Nothing here enumerates a host's shells: a probe is a
    shell run, and running every shell a host names on the chance
    someone logs in with one is a cost with no answer attached.

    :param Iterable[tuple[str, str]] pairs: The (shell, home)
        combinations to observe
    :param Optional[str] dropper: A user to run each probe as through
        a login su, or None to run it bare
    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (  # noqa: E501
        SHELL_COMMAND_SPEC,
    )

    requests = []
    for shell, home in pairs:
        asked = process_command_spec(
            SHELL_COMMAND_SPEC,
            cmd_type="shell_config",
            shell=shell,
            home=home,
        )
        for request in asked:
            _named(request, shell)
            if dropper is not None:
                # A login su first, so the shell is asked out of a
                # reset environment rather than out of whatever the
                # connection and the become left behind
                request["command"] = (
                    "su",
                    "-",
                    dropper,
                    "-c",
                    format_command(request["command"]),
                )
                request[EVIDENCE] = sorted({*request[EVIDENCE], "su"})
        requests.extend(asked)

    return requests


def process_shell_command_results(
    cmds_completed: list[dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Read what each combination produced out of a batch's results.

    Two kinds of probe answer here and they are filed differently for
    one reason: whether the probe was told what it was running.  A
    probe of a named shell out of a named home is filed by what it was
    asked - we chose both, so we know both.  A probe run through a
    login su runs the user's own shell out of their own home and is
    told neither, so it is filed by what its own login environment
    answered: the probe is the evidence for its own placement.

    Either way the placement is removed before the row is published.
    The shell is the entry key and the home is the row key, so a field
    repeating one of them would echo the key it was filed under.

    Each shell also gets the record of what was asked of it - of it,
    not of the batch: a shell observed out of two homes was asked the
    same way twice and a shell nobody probed was asked nothing, so a
    record built from every probe in the batch and copied onto each
    shell would tell one shell what another was asked. The shell the
    probe turned out to run is named on its own row's record, which is
    the only place that knows it.

    :param list[dict[str, Any]] cmds_completed: Command results
    :returns tuple[dict[str, dict[str, dict[str, Any]]],
        dict[str, dict[str, Any]]]: What was observed, keyed by shell
        and then by home, and what was consulted, keyed by shell
    """
    processed = process_all_command_results(cmds_completed)

    observed: dict[str, dict[str, dict[str, Any]]] = {}
    consulted: dict[str, set[str]] = {}

    for cmd_type in ("shell_config", "shell_login"):
        results = processed.get(cmd_type)
        if results is None:
            continue
        if isinstance(results, dict):
            results = [results]

        for result in results:
            if not isinstance(result, dict):
                continue
            config = result.get("parsed")
            if not config:
                continue

            placement = config.pop(SHELL_FILING, None) or {}
            if cmd_type == "shell_login":
                shell = placement.get(SHELL_ENV_FILING)
                home = placement.get("HOME")
            else:
                args = result.get("args") or {}
                shell = args.get("shell")
                home = args.get("home")

            if shell and home and config:
                observed.setdefault(shell, {})[home] = config
                # The shell a login probe turned out to run is named
                # here, because here is where it became known
                consulted.setdefault(shell, set()).update(
                    command_names(result) + [posixpath.basename(shell)]
                )

    return observed, {
        shell: compose_evidence(commands=names)
        for shell, names in consulted.items()
    }


def compose_shells(
    named: Optional[Sequence[str]] = None,
    observed: Optional[dict[str, dict[str, dict[str, Any]]]] = None,
    evidence: Optional[dict[str, dict[str, Any]]] = None,
    builtins: Optional[dict[str, Sequence[str]]] = None,
    builtins_evidence: Optional[dict[str, Any]] = None,
) -> dict[str, dict[str, Any]]:
    """Compose the canonical shells fact from both halves.

    Keyed by shell path, so ``user.shell in o0_shells`` reads as it
    always did: the keys are the login shells the host names, and a
    shell that was probed without being named is a key too, because
    the host answered for it.

    Under each shell, the homes it was observed out of, keyed by home
    under ``homes`` - a mapping of its own, so a home path is never a
    key beside a field of the shell.  Each home holds what that
    combination produced directly: the ``env`` it had set, the
    ``umask`` it would create files under, the ``locale`` it reported
    and the ``aliases`` it had defined.  Beside ``homes``, the shell's
    own facts: the ``builtins`` it answers itself, intrinsic to the
    binary because no home changes what a shell is built out of, and
    ``binary``, the file its name finally resolves to.

    One ``evidence`` record per shell, the union of everything asked
    of it - the login probes out of each home and whatever enumerated
    the builtins - because a shell asked three ways was asked about
    one shell.  A shell nothing was asked of has none:
    one shell may be observed out of two homes, and the fact is a fact
    about the pair.  A shell nothing was observed of keeps its key
    with an empty mapping under it - the key is the host's claim that
    this is a login shell, and the empty value is the truthful
    statement that nothing has been run to find out what it does, so
    there is nothing for evidence to support.  That claim's own
    provenance is the ``/etc/shells`` entry of ``o0_paths``, which
    holds the names under its ``config``.

    :param Optional[Sequence[str]] named: The login shells the host
        names, as ``/etc/shells`` gave them
    :param Optional[dict[str, dict[str, dict[str, Any]]]] observed:
        What each probed combination produced, keyed by shell and home
    :param Optional[dict[str, dict[str, Any]]] evidence: What each
        shell was asked with, keyed by shell, folded into that shell's
        own record
    :param Optional[dict[str, Sequence[str]]] builtins: The commands
        each shell answers itself, keyed by shell
    :param Optional[dict[str, Any]] builtins_evidence: What enumerated
        the builtins, folded into the same record
    :returns dict[str, dict[str, Any]]: The shells fact
    """
    observed = observed or {}

    shells: dict[str, dict[str, Any]] = {shell: {} for shell in (named or [])}

    for shell in sorted(observed):
        entry = shells.setdefault(shell, {})
        homes = entry.setdefault("homes", {})
        for home in sorted(observed[shell]):
            homes[home] = dict(observed[shell][home])
        _consulted(entry, (evidence or {}).get(shell))

    # A builtin is the shell binary answering for itself, so it sits
    # at the shell rather than under a home: no home changes which
    # commands a shell is built out of
    for shell in sorted(builtins or {}):
        entry = shells.setdefault(shell, {})
        entry["builtins"] = sorted(set(builtins[shell]))
        _consulted(entry, builtins_evidence)

    return shells


def _consulted(
    entry: dict[str, Any], evidence: Optional[dict[str, Any]]
) -> None:
    """Fold what a probe consulted into the shell's own record.

    One record per shell, the union of everything asked of it.  A
    shell observed out of two homes was asked the same way twice and a
    shell whose builtins were enumerated was asked a second way, and
    all of it is provenance for the one entry.

    :param dict[str, Any] entry: The shell's entry, edited in place
    :param Optional[dict[str, Any]] evidence: What was consulted, or
        None where the caller has nothing to add
    """
    if evidence is None:
        return

    merge_evidence(
        entry.setdefault(EVIDENCE, {}),
        {
            kind: (list(named) if isinstance(named, list) else dict(named))
            for kind, named in evidence.items()
        },
    )


def name_shell_binaries(
    shells: dict[str, dict[str, Any]],
    paths: Optional[dict[str, Any]] = None,
) -> dict[str, dict[str, Any]]:
    """Point each shell at the file its name finally resolves to.

    A key here is the name the host uses, and the name is what decides
    behavior: bash invoked as ``sh`` is in POSIX mode and invoked as
    ``rbash`` is restricted, so ``/bin/sh`` and ``/usr/bin/bash`` are
    two observations of one file and both are worth keeping.  What the
    two have in common is the file, and ``binary`` names it - the last
    step of the chain the path store already walked, copied rather
    than walked again.

    A shell the store describes without a chain resolves to itself,
    which is what a path that is nothing but itself resolves to.  A
    shell the store never described gets no pointer: nothing walked
    it, and a self-pointer would assert a resolution nobody checked.

    :param dict[str, dict[str, Any]] shells: The shells fact, edited
        in place
    :param Optional[dict[str, Any]] paths: The o0_paths store
    :returns dict[str, dict[str, Any]]: The shells fact
    """
    store = paths or {}

    for shell, entry in shells.items():
        described = store.get(canonicalize(shell))
        if not isinstance(described, dict):
            continue

        chain = described.get("resolution")
        if isinstance(chain, list) and chain:
            entry["binary"] = chain[-1]
        elif "type" in described:
            entry["binary"] = canonicalize(shell)

    return shells


__all__ = [
    "SHELL_ALIAS_MARKER",
    "SHELL_ENV_VARS",
    "SHELL_DEFAULT",
    "SHELL_END_MARKER",
    "SHELL_ENV_MARKER",
    "SHELL_LOCALE_MARKER",
    "SHELL_RCS",
    "SHELL_SYSTEM_HOME",
    "SHELL_UMASK_MARKER",
    "compose_shells",
    "get_shell_command_requests",
    "get_shell_login_requests",
    "name_shell_binaries",
    "parse_shells",
    "process_shell_command_results",
]
