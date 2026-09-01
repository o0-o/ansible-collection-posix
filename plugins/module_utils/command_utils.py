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

"""Command utilities for POSIX action plugins.

Standalone functions for command formatting, argument sanitization,
interpreter detection, shell quoting, and command lookup processing.
These functions are designed to be used independently of ActionBase
classes.
"""

from __future__ import annotations

import posixpath
import shlex
from copy import deepcopy
from typing import Any, Optional, Union

from ansible.module_utils.common.text.converters import to_native

from ansible_collections.o0_o.utils.plugins.module_utils import (
    typechecked,
)

from ansible_collections.o0_o.core.plugins.module_utils.evidence_utils import (  # noqa: E501
    EVIDENCE,
    compose_evidence,
)
from ansible_collections.o0_o.posix.plugins.module_utils.path_utils import (
    compose_paths,
)

# The shell the lookups answer in.  Every probe runs through the
# target's ``/bin/sh``, so a builtin it answers with and an alias it
# expands are facts about that file rather than about the command
# name, and they file under its entry.
ANSWERING_SHELL = "/bin/sh"

# What every one of these entries was consulted with. The lookups are
# one command asked once per name, so an entry that came out of them
# names that command and nothing else.
LOOKUP_COMMAND = "command"


def format_command(cmd: Union[str, list[str]]) -> str:
    """Convert a command to a shell-safe string.

    Handles both string and list inputs, properly quoting list
    elements for shell execution. List elements are automatically
    converted to native strings to handle non-string types like
    integers or Path objects.

    :param cmd: Command as string or list of arguments
    :returns str: Shell-safe command string
    """
    if isinstance(cmd, str):
        # Validate syntax and normalize quoting by tokenizing
        # and re-joining
        cmd = shlex.split(cmd)
    else:
        # Convert all list elements to native strings
        cmd = [
            to_native(
                arg, errors="surrogate_or_strict", nonstring="simplerepr"
            )
            for arg in cmd
        ]
    try:
        # Use shlex.join() if available (Python 3.8+)
        return shlex.join(cmd)
    except AttributeError:
        # Python < 3.8 fallback
        return " ".join(shlex.quote(str(arg)) for arg in cmd)


def is_interpreter_missing(result: dict[str, Any]) -> bool:
    """Check if failure was likely caused by a missing Python interpreter.

    :param dict[str, Any] result: A result dict from _execute_module or
        fallback command
    :returns bool: True if failure likely due to missing Python,
        else False
    """
    if not isinstance(result, dict):
        return False

    if result.get("rc") != 127:
        return False

    msg = result.get("msg", "")
    stderr = result.get("stderr", "")
    module_stderr = result.get("module_stderr", "")
    module_stdout = result.get("module_stdout", "")

    # Check all text fields for interpreter errors
    text_to_check = " ".join(
        [
            str(msg) if isinstance(msg, str) else "",
            str(stderr) if isinstance(stderr, str) else "",
            str(module_stderr) if isinstance(module_stderr, str) else "",
            str(module_stdout) if isinstance(module_stdout, str) else "",
        ]
    ).lower()

    # Ansible's standard error message
    canary_str = (
        "The module failed to execute correctly, you probably need to set "
        "the interpreter"
    )

    # Check for the standard canary or signs of missing Python
    if canary_str.lower() in text_to_check:
        return True

    # Check for shell error indicating Python not found
    # Examples: "/usr/bin/python3: not found", "python: not found"
    python_patterns = [
        "python: not found",
        "python2: not found",
        "python3: not found",
    ]

    if any(pattern in text_to_check for pattern in python_patterns):
        return True

    return False


def sanitize_args(args: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the argument dictionary with all None values removed.

    This is useful when passing arguments to Ansible modules that
    enforce mutually exclusive parameters or expect missing values
    to be omitted rather than explicitly set to null/None.

    :param dict[str, Any] args: Dictionary of module arguments to sanitize
    :returns dict[str, Any]: A new dictionary with all None values removed
    """
    return {k: v for k, v in args.items() if v is not None}


def quote(s: str, shell: Optional[Any] = None) -> str:
    """Quote a string for safe use in shell commands.

    Uses the provided shell's quoting logic if available (e.g., for
    non-POSIX shells), falling back to Python's ``shlex.quote()`` for
    standard POSIX-compatible escaping.

    :param str s: The string to quote
    :param Optional[Any] shell: Shell plugin instance with quote() method.
        If None, uses shlex.quote()
    :returns str: The safely quoted string
    """
    if shell is not None:
        quote_fn = getattr(shell, "quote", None)
        if quote_fn is not None:
            return quote_fn(s)
    return shlex.quote(s)


@typechecked
def process_command_lookups(
    lookup_results_list: list[dict],
    uid: Optional[int] = None,
) -> tuple[dict[str, Any], list[str], list[str], list[Exception]]:
    """Compose command lookups into one o0_paths observation.

    A command that resolved is a fact about the file it resolved to,
    so it files under that path rather than under the name it was
    asked for, recording ``executable`` for the uid that asked:
    ``command -v`` names a pathname the shell would run, which is that
    shell answering the same question ``test -x`` answers, and the
    answer belongs to whoever the shell was running as.

    Which is why a sweep that could not learn its own uid records no
    executable claim at all.  A row is one uid's answer, and a row
    with nobody's name on it is not one; the entry is still filed,
    because the path was reached and that much is known.

    A command that did not resolve was not found in any directory the
    lookups searched, and the resolutions themselves name those
    directories, so the miss files a null - confirmed absent - at that
    command's name in each of them.  A name that cannot be a file, a
    dot or a path of its own, names no candidate and files nothing.

    Builtins are not paths at all.  A command the shell answers
    itself resolves to no file, so it is answered back to the caller
    to file on the shell rather than filed here - the store is facts
    about paths, and which commands a shell is built out of is a fact
    about the shell.  An alias is not a path either and is not
    answered back: it comes from a rc file, so it belongs to a shell
    and a home together and is what the shell-context probe reports.

    The answering shell keeps an entry all the same, empty where
    nothing else was learned about the file.  It ran the probes, which
    is as much as anything can say that a file is there, so it is
    never one of the misses even where the name ``sh`` did not resolve
    in the search path.

    Each path is observed once and composed whole, because the store
    replaces an entry rather than blending fields into it.  A path the
    host answered with that cannot key the store is refused as an
    error rather than taking the sweep down with it.

    :param list[dict] lookup_results_list: List of lookup_command result
        dicts, each containing 'args' with 'cmd' key and 'parsed' output
    :param Optional[int] uid: The uid the lookups ran as, where it was
        determined
    :returns tuple[dict[str, Any], list[str], list[str],
        list[Exception]]: The o0_paths observation, the commands the
        answering shell answers itself (sorted), the commands that did
        not resolve (sorted), and the errors the lookups raised
    """
    builtins: list[str] = []
    resolved: set[str] = set()
    missing: list[str] = []
    errors: list[Exception] = []

    lookup_results = {}
    for lookup in lookup_results_list:
        cmd = lookup["args"]["cmd"]
        lookup_results[cmd] = lookup

    # If `command` itself is missing, no other lookup can be trusted
    command_missing = (
        "command" in lookup_results
        and lookup_results["command"].get("parsed") is None
    )

    if command_missing:
        missing.append("command")
    else:
        for cmd, cmd_result in lookup_results.items():
            parsed = cmd_result.get("parsed")

            # Command not found
            if parsed is None:
                missing.append(cmd)
                continue

            # An alias names no file and is not a fact about one.
            # What a shell aliases comes out of a rc file, so it
            # belongs to that shell and that home together and the
            # shell-context probe is what reports it
            if parsed.startswith(f"alias {cmd}="):
                continue

            # Path
            if parsed.startswith("/"):
                resolved.add(parsed)

            # Builtin (output equals command name)
            elif parsed.startswith(cmd):
                builtins.append(cmd)

            # Unexpected output format
            else:
                errors.append(
                    RuntimeError(
                        f"Unexpected 'command -v {cmd}' output: {repr(parsed)}"
                    )
                )

    # Every entry these lookups compose was reached the same way, so
    # every one of them names the same command. Only commands: a
    # lookup reads no file
    consulted = compose_evidence(commands=[LOOKUP_COMMAND])

    claim: dict[str, Any] = {EVIDENCE: consulted}
    if uid is not None:
        claim["executable"] = {str(uid): True}

    entries: dict[str, Optional[dict[str, Any]]] = {
        path: deepcopy(claim) for path in resolved
    }

    # The shell answered, so its entry is written before the misses
    # and is not one of them, saying nothing but that it answered
    # where the lookups learned nothing else about the file
    entries.setdefault(ANSWERING_SHELL, {EVIDENCE: deepcopy(consulted)})

    searched = sorted({posixpath.dirname(path) for path in resolved})
    for cmd in missing:
        if "/" in cmd or cmd in (".", ".."):
            continue
        for directory in searched:
            entries.setdefault(posixpath.join(directory, cmd), None)

    paths: dict[str, Any] = {}
    for path in sorted(entries):
        try:
            paths = compose_paths(paths, {path: entries[path]})
        except ValueError as exc:
            errors.append(exc)

    return paths, sorted(set(builtins)), sorted(missing), errors
