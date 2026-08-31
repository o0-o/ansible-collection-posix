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

import re

from typing import Any, Iterable, Optional, Sequence, Union

from ansible_collections.o0_o.core.plugins.module_utils import (
    process_all_command_results,
    process_command_spec,
)

from ansible_collections.o0_o.posix.plugins.module_utils.env_utils import (
    POSIX_ENV_VARS,
)
from ansible_collections.o0_o.posix.plugins.module_utils.filter_utils import (
    decode_declared_content,
)
from ansible_collections.o0_o.posix.plugins.module_utils.locale_utils import (
    _parse_locale,
)
from ansible_collections.o0_o.utils.plugins.module_utils import strip_comments

# The home a probe of the system layer uses.  Documented, canonical,
# and present on every POSIX host without ever being a directory.
SHELL_SYSTEM_HOME = "/dev/null"

# The shell a producer probes when it was not told which
SHELL_DEFAULT = "/bin/sh"

# What the probe prints between the three things it asks for, and
# after the last of them.  A login shell may print anything it likes
# before the first marker - a dot file that echoes is still a dot file
# that ran - so the first marker is where the answer starts, and the
# last is how the parser knows the script reached its end.
SHELL_UMASK_MARKER = "@UMASK@"
SHELL_ENV_MARKER = "@ENV@"
SHELL_LOCALE_MARKER = "@LOCALE@"
SHELL_END_MARKER = "@END@"

# Every exit status the probe reads as an answer rather than a fault.
# 126 and 127 are the shell's for a shell that cannot be run and one
# that is not there, and both mean the same thing to the fact: no row.
SHELL_RCS = [0, 126, 127]

# What a variable may be named, which is how a continuation line is
# told from the start of the next variable
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


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


def _parse_env_block(text: str) -> dict[str, str]:
    """Read an ``env`` block into the POSIX variables it printed.

    A value may hold newlines, and ``env`` prints them as newlines, so
    a line that does not begin with a variable name and an equals sign
    continues the value before it rather than starting a new one.

    Only the variables IEEE Std 1003.1 names are kept, which is the
    same environment ``o0_users`` publishes.  A shell's environment is
    a place secrets live, and an observation is not a reason to copy
    them into a fact.

    :param str text: The block between the env and locale markers
    :returns dict[str, str]: The POSIX variables the shell had set
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

    return {name: values[name] for name in POSIX_ENV_VARS if name in values}


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
    locale_text, _marker, _after = rest.partition(SHELL_END_MARKER)

    config: dict[str, Any] = {}

    from ansible_collections.o0_o.posix.plugins.module_utils.limits_utils import (  # noqa: E501
        _parse_umask,
    )

    umask, _errors = _parse_umask(umask_text, "")
    if umask is not None:
        config["umask"] = umask

    env = _parse_env_block(env_text)
    if env:
        config["env"] = env

    locale, _errors = _parse_locale(locale_text, "")
    if locale:
        config["locale"] = locale

    return (config or None), None


def get_shell_command_requests(
    pairs: Iterable[tuple[str, str]],
) -> list[dict[str, Any]]:
    """Build command requests for the combinations named.

    One request per pair, and only for the pairs a caller asked
    about.  Nothing here enumerates a host's shells: a probe is a
    shell run, and running every shell a host names on the chance
    someone logs in with one is a cost with no answer attached.

    :param Iterable[tuple[str, str]] pairs: The (shell, home)
        combinations to observe
    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (  # noqa: E501
        SHELL_COMMAND_SPEC,
    )

    requests = []
    for shell, home in pairs:
        requests.extend(
            process_command_spec(
                SHELL_COMMAND_SPEC,
                cmd_type="shell_config",
                shell=shell,
                home=home,
            )
        )

    return requests


def process_shell_command_results(
    cmds_completed: list[dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Read what each combination produced out of a batch's results.

    :param list[dict[str, Any]] cmds_completed: Command results
    :returns dict[str, dict[str, dict[str, Any]]]: What was observed,
        keyed by shell and then by home
    """
    processed = process_all_command_results(cmds_completed)

    results = processed.get("shell_config")
    if results is None:
        return {}
    if isinstance(results, dict):
        results = [results]

    observed: dict[str, dict[str, dict[str, Any]]] = {}
    for result in results:
        if not isinstance(result, dict):
            continue
        config = result.get("parsed")
        if not config:
            continue
        args = result.get("args") or {}
        shell = args.get("shell")
        home = args.get("home")
        if shell and home:
            observed.setdefault(shell, {})[home] = config

    return observed


def compose_shells(
    named: Optional[Sequence[str]] = None,
    observed: Optional[dict[str, dict[str, dict[str, Any]]]] = None,
    evidence: Optional[dict[str, Any]] = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Compose the canonical shells fact from both halves.

    Keyed by shell path, so ``user.shell in o0_shells`` reads as it
    always did: the keys are the login shells the host names, and a
    shell that was probed without being named is a key too, because
    the host answered for it.

    Under each shell, a row per home probed, holding the ``config``
    that combination produced and the ``evidence`` for it.  A row is
    where the provenance sits because a row is where a probe happened:
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
    :param Optional[dict[str, Any]] evidence: What the observations
        were made with, named on every row they produced
    :returns dict[str, dict[str, dict[str, Any]]]: The shells fact
    """
    observed = observed or {}

    shells: dict[str, dict[str, dict[str, Any]]] = {
        shell: {} for shell in (named or [])
    }

    for shell in sorted(observed):
        rows = shells.setdefault(shell, {})
        for home in sorted(observed[shell]):
            row: dict[str, Any] = {"config": observed[shell][home]}
            if evidence is not None:
                row["evidence"] = {
                    kind: list(origins) for kind, origins in evidence.items()
                }
            rows[home] = row

    return shells


__all__ = [
    "SHELL_DEFAULT",
    "SHELL_END_MARKER",
    "SHELL_ENV_MARKER",
    "SHELL_LOCALE_MARKER",
    "SHELL_RCS",
    "SHELL_SYSTEM_HOME",
    "SHELL_UMASK_MARKER",
    "compose_shells",
    "get_shell_command_requests",
    "parse_shells",
    "process_shell_command_results",
]
