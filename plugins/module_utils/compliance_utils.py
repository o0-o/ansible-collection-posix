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

"""POSIX/SUS compliance processing utilities.

Constants and processing functions for gathering and processing POSIX,
X/Open, and SUS compliance information.

Every verdict this publishes names what decided it, in the one
provenance vocabulary the collection speaks: ``evidence``, keyed by
kind of origin.  Compliance reads no files, so it carries the two
kinds it attempts - ``commands``, the names of the probes it
consulted, and ``config``, the POSIX configuration variables it read
and the values they answered with, keyed and typed the way
``o0_os.config`` keys and types them.  A value lives in the evidence
rather than being pointed at, because a compliance gather can run
without the configuration subset and a support that dangles is no
support at all.
"""

from __future__ import annotations

from typing import Any

from ansible_collections.o0_o.utils.plugins.module_utils import (
    typechecked,
)

from ansible_collections.o0_o.core.plugins.module_utils import (
    process_all_command_results,
    process_command_spec,
)

from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (
    COMMAND_SPEC,
    COMPLIANCE_COMMAND_SPEC,
)
from ansible_collections.o0_o.posix.plugins.module_utils.command_utils import (
    ANSWERING_SHELL,
    LOOKUP_COMMAND,
    process_command_lookups,
)
from ansible_collections.o0_o.posix.plugins.module_utils.evidence_utils import (  # noqa: E501
    command_name,
    compose_evidence,
    merge_evidence,
    name_origins,
)
from ansible_collections.o0_o.posix.plugins.module_utils.getconf_utils import (
    _answered,
    _parse_getconf,
)
from ansible_collections.o0_o.posix.plugins.module_utils.id_utils import (
    get_effective_uid_command_requests,
    process_effective_uid_results,
)
from ansible_collections.o0_o.posix.plugins.module_utils.shells_utils import (
    compose_shells,
)

# What this module is called, which is what a fact it composes names
# as one of the producers that made it
FQCN = "o0_o.posix.compliance"

# Standards metadata - used to initialize compliance dict with descriptions
SUS = {
    "name": "Single UNIX Specification",
    "abbreviation": "SUS",
    "description": "Unified UNIX standard combining POSIX with XSI extensions",
}

POSIX = {
    "name": "Portable Operating System Interface",
    "abbreviation": "POSIX",
    "description": "IEEE standard for compatibility between operating systems",
}

XSH = {
    "name": "System Interfaces",
    "abbreviation": "XSH",
    "description": "POSIX System Interfaces and Headers",
}

XCU = {
    "name": "Shell & Utilities",
    "abbreviation": "XCU",
    "description": "POSIX Shell and Utilities",
}

XSI = {
    "name": "X/Open System Interfaces",
    "abbreviation": "XSI",
    "description": "SUS X/Open System Interfaces (UNIX extensions to POSIX)",
}

# Every utility POSIX.1-2017 defines, as its own index lists them.
# This is the authority for whether a name is a POSIX utility at all,
# and the required lists below are held to it - which is what stops a
# conformance list from asserting something the standard never asked
# for.  Source: IEEE Std 1003.1-2017, Shell and Utilities volume,
# Utilities index
# <https://pubs.opengroup.org/onlinepubs/9699919799/idx/utilities.html>
POSIX_UTILITIES = frozenset(
    {
        "admin", "alias", "ar", "asa", "at", "awk",
        "basename", "batch", "bc", "bg", "c99", "cal",
        "cat", "cd", "cflow", "chgrp", "chmod", "chown",
        "cksum", "cmp", "comm", "command", "compress", "cp",
        "crontab", "csplit", "ctags", "cut", "cxref", "date",
        "dd", "delta", "df", "diff", "dirname", "du",
        "echo", "ed", "env", "ex", "expand", "expr",
        "false", "fc", "fg", "file", "find", "fold",
        "fort77", "fuser", "gencat", "get", "getconf", "getopts",
        "grep", "hash", "head", "iconv", "id", "ipcrm",
        "ipcs", "jobs", "join", "kill", "lex", "link",
        "ln", "locale", "localedef", "logger", "logname", "lp",
        "ls", "m4", "mailx", "make", "man", "mesg",
        "mkdir", "mkfifo", "more", "mv", "newgrp", "nice",
        "nl", "nm", "nohup", "od", "paste", "patch",
        "pathchk", "pax", "pr", "printf", "prs", "ps",
        "pwd", "qalter", "qdel", "qhold", "qmove", "qmsg",
        "qrerun", "qrls", "qselect", "qsig", "qstat", "qsub",
        "read", "renice", "rm", "rmdel", "rmdir", "sact",
        "sccs", "sed", "sh", "sleep", "sort", "split",
        "strings", "strip", "stty", "tabs", "tail", "talk",
        "tee", "test", "time", "touch", "tput", "tr",
        "true", "tsort", "tty", "type", "ulimit", "umask",
        "unalias", "uname", "uncompress", "unexpand", "unget", "uniq",
        "unlink", "uucp", "uudecode", "uuencode", "uustat", "uux",
        "val", "vi", "wait", "wc", "what", "who",
        "write", "xargs", "yacc", "zcat",
    }
)

# The utilities that belong to an option group rather than to the
# mandatory base.  A conformant system need not have any of these, so
# requiring one would report a conforming host as failing - which is
# exactly what requiring tar did.  Membership is the standard's own
# option grouping, and macOS, a certified UNIX, lacks the SCCS, the
# FORTRAN and the batch sets entirely.
POSIX_OPTIONAL_UTILITIES = frozenset(
    {
        # Batch Environment Services
        "qalter", "qdel", "qhold", "qmove", "qmsg", "qrerun",
        "qrls", "qselect", "qsig", "qstat", "qsub",
        # Source Code Control System
        "admin", "delta", "get", "prs", "rmdel", "sact", "sccs",
        "unget", "val", "what",
        # C-language and FORTRAN development
        "ar", "asa", "c99", "ctags", "fort77", "lex", "make", "nm",
        "strip", "yacc",
        # UUCP
        "uucp", "uustat", "uux",
        # User Portability Utilities
        "ex", "man", "mesg", "more", "talk", "vi",
        # X/Open System Interfaces, which the XSI list below requires
        # of a host claiming that option and this list does not
        "cflow", "cxref", "fuser", "gencat", "ipcrm", "ipcs",
        "link", "unlink",
    }
)

# The special built-in utilities, which a conformant shell provides
# itself and which no PATH search can find.  Source: IEEE Std
# 1003.1-2017, Shell and Utilities volume, section 2.14.
XCU_SPECIAL_BUILTINS = frozenset(
    {
        ":", ".", "break", "continue", "eval", "exec", "exit",
        "export", "readonly", "return", "set", "shift", "times",
        "trap", "unset",
    }
)

# The shell's reserved words, which are grammar rather than utilities.
# A shell that does not know them is not a POSIX shell, and
# ``command -v`` answers for them, so they are worth asking about -
# but they are asked about as what they are.  Source: IEEE Std
# 1003.1-2017, Shell and Utilities volume, section 2.4.
XCU_RESERVED_WORDS = frozenset(
    {
        "case", "do", "done", "elif", "else", "esac", "fi", "for",
        "if", "in", "then", "until", "while",
    }
)

# The utilities a conformant host must have, every one of them in
# POSIX_UTILITIES and none of them in an option group.  ``[`` is here
# under its own name because the standard documents it on the ``test``
# page rather than indexing it separately.
#
# This is a subset of the mandatory base rather than the whole of it:
# every name here has been checked against the standard's own index
# and against its option markers, and a utility whose option-group
# membership has not been checked is left out.  Leaving one out
# under-reports a gap; putting one in wrongly reports a conformant
# host as failing, which is what requiring tar did.
XCU_REQUIRED_UTILITIES = frozenset(
    {
        # Regular built-in utilities
        "alias", "bg", "cd", "command", "false", "fg", "getopts",
        "hash", "jobs", "kill", "pwd", "read", "true", "type",
        "ulimit", "umask", "unalias", "wait",
        # File utilities
        "basename", "cat", "chmod", "chown", "cp", "dd", "df",
        "dirname", "du", "ln", "ls", "mkdir", "mv", "rm", "rmdir",
        "touch",
        # Text processing
        "awk", "cut", "diff", "grep", "head", "paste", "sed", "sort",
        "tail", "tr", "uniq", "wc",
        # Other utilities
        "[", "env", "expr", "id", "printf", "test", "tty", "uname",
        "xargs",
        # Base utilities the earlier sample left out. at, batch and
        # crontab carry no option marker over their synopsis, so a
        # host without them is not conformant; pax is the standard's
        # archiver and getconf is how a host answers for its own
        # configuration, and both were wrongly filed under XSI.
        "at", "batch", "crontab", "getconf", "pax",
    }
)

# Required commands for XCU (Shell & Utilities) compliance
XCU_REQUIRED_COMMANDS = frozenset(
    {"sh"}
    | XCU_SPECIAL_BUILTINS
    | XCU_RESERVED_WORDS
    | XCU_REQUIRED_UTILITIES
)

# Required commands for XSI (X/Open System Interfaces) compliance.
# Each of these carries the [XSI] marker over its whole synopsis in
# the standard, which is what makes it required of a host claiming the
# option and of no other host.  getconf and pax were here and are not
# XSI at all - both are mandatory base utilities, so a host lacking
# one has an XCU gap and reading it as an XSI gap named the wrong
# standard.
XSI_REQUIRED_COMMANDS = frozenset(
    {
        "fuser",
        "ipcrm",
        "ipcs",
        "link",
        "unlink",
    }
)


@typechecked
def get_compliance_command_requests() -> list[dict[str, Any]]:
    """Build command requests for compliance checks.

    Generates one `command -v` request per required command using list
    kwargs, plus getconf and sh_test commands from COMPLIANCE_COMMAND_SPEC.

    The effective uid rides with them, because what ``command -v``
    answers is what the shell running it would run, and that answer
    belongs to whoever the shell was running as.  One more command in
    a batch of dozens is what it costs to key the claim by name rather
    than by nobody.

    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    requests = list(get_effective_uid_command_requests())

    # Command lookups - one request per command via list kwarg
    all_cmds = list(XCU_REQUIRED_COMMANDS | XSI_REQUIRED_COMMANDS)
    lookup_requests = process_command_spec(
        COMMAND_SPEC,
        cmd_type="lookup_command",
        cmd=all_cmds,
    )
    requests.extend(lookup_requests)

    # Getconf and sh_test commands
    compliance_requests = process_command_spec(COMPLIANCE_COMMAND_SPEC)
    requests.extend(compliance_requests)

    return requests


@typechecked
def missing_commands(compliance: dict[str, Any]) -> list[str]:
    """Derive the utilities a host was asked for and did not have.

    Every command the sweep probes belongs to XCU or to XSI, and a
    standard records each of its own misses beside its verdict, so the
    two lists already hold the whole answer.  Deriving it here is what
    lets a fact namespace of absences retire: an absence stored beside
    the evidence for it is a second copy waiting to drift from the
    first.

    :param dict[str, Any] compliance: The o0_os.compliance fact
    :returns list[str]: The commands that did not resolve, sorted
    """
    missing: set[str] = set()
    for standard in ("xcu", "xsi"):
        missing.update(compliance.get(standard, {}).get("missing") or [])
    return sorted(missing)


@typechecked
def _name_command(evidence: dict[str, Any], command: Any) -> None:
    """Name one probe on an evidence record, once.

    What is named is the command, not the invocation: XSI is asked for
    two variables and XCU looks for ninety utilities, and a record
    that spelled every one of those out would bury the answer under
    its own repetitions.  What was asked is in ``config`` and what was
    missing is in ``missing``; this says what was consulted.

    :param dict[str, Any] evidence: The record to add to, edited in
        place
    :param Any command: The command as the request carried it
    """
    name = command_name(command)
    if name is not None and name not in evidence["commands"]:
        evidence["commands"].append(name)
        evidence["commands"].sort()


@typechecked
def _record_probe(standard: dict[str, Any], result: dict[str, Any]) -> None:
    """Name one getconf probe as evidence of what it decided.

    The probe is a command and what it read is a POSIX configuration
    variable, so both kinds of the one record are written here: the
    command that ran, and the variable it answered with under the
    value it answered.  The value is typed the way ``o0_os.config``
    types it - an integer where the host printed a number - because
    the two are the same fact read at two moments and a consumer
    joining them by variable name has to find one answer, not two
    spellings of it.

    A variable the host would not answer is named by the command that
    asked for it and left out of the configuration, which is what
    leaving one out means everywhere else: the host was asked and said
    nothing.  A variable it has and does not limit answers
    ``undefined``, which is an answer, so it keeps its key valued
    null.

    :param dict[str, Any] standard: One standard's compliance dict,
        edited in place
    :param dict[str, Any] result: The processed result of one probe
    """
    evidence = standard["evidence"]
    command = result.get("command") or ()
    _name_command(evidence, command)

    if len(command) < 2 or not _answered(result):
        return

    value, _errors = _parse_getconf(0, result.get("stdout") or "", "")
    evidence["config"][command[1]] = value


@typechecked
def _borrow_evidence(
    standard: dict[str, Any],
    *decided_by: dict[str, Any],
) -> None:
    """Give a derived standard the evidence of what derives it.

    POSIX and SUS run no probe of their own: each is a verdict on the
    standards it is composed of, so whatever decided those decided it,
    and it names their evidence as its own.  That is what lets a
    consumer read one standard's support and the support for it
    without knowing which other standards add up to it.

    :param dict[str, Any] standard: The derived standard, edited in
        place
    :param dict[str, Any] decided_by: The standards it is composed of,
        in composition order
    """
    for source in decided_by:
        merge_evidence(standard["evidence"], source["evidence"])


@typechecked
def process_all_compliance_command_results(
    cmds_completed: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[Exception]]:
    """Process compliance command results through their parsers.

    Takes command results from run plugin, calls the appropriate
    parser for each command type, and merges the partial results into
    the two facts both compliance producers publish:
    ``o0_os.compliance``, ``o0_paths`` and ``o0_shells``.

    What the sweep learned about the commands it looked for is mostly
    a set of facts about paths, so it lands in the path store: at the
    path a command resolved to, an executable row keyed by the uid the
    lookups ran as, and a miss as a null at each path it was not at.
    A builtin is not a fact about a path - it resolved to no file -
    but about the shell that answered for it, so it lands on that
    shell in ``o0_shells``.  A command the host
    does not have is recorded once, in the ``missing`` list of the
    standard that requires it, and ``missing_commands`` derives the
    list back out.

    Every verdict names what decided it in ``evidence``.  A standard
    probed by getconf names the command that asked and the variable it
    answered; a standard that records a utility as missing names the
    lookup that missed it; and POSIX and SUS, which probe nothing of
    their own, name the evidence of the standards they are composed
    of.  The namespace's own verdict, ``sh_posix_compliant``, names
    its probe the same way beside it.

    :param list[dict[str, Any]] cmds_completed: List of command result
        dicts, each containing 'type', 'implementation', 'rc', 'stdout',
        and optionally 'parser' from the command spec
    :returns tuple[dict[str, Any], list[Exception]]: Tuple of
        (facts, errors) where facts holds the o0_os, o0_paths and
        o0_shells namespaces
    """
    # Initialize compliance dict with standard metadata
    compliance = {
        "xsh": XSH.copy(),
        "xcu": XCU.copy(),
        "xsi": XSI.copy(),
        "posix": POSIX.copy(),
        "sus": SUS.copy(),
    }

    # Both kinds a standard is decided by are always attempted, so
    # both are always present and a kind that decided nothing is
    # empty rather than absent. The third kind of the vocabulary,
    # files, is left off: compliance reads none.
    for entry in compliance.values():
        entry["evidence"] = {"commands": [], "config": {}}

    # Standards with required commands
    for standard in ["xcu", "xsi"]:
        compliance[standard]["missing"] = []

    # The namespace has one verdict of its own - the behavioral shell
    # probe - so it names that probe beside it, in the same shape a
    # standard names its own. Only a command: the probe's answer is
    # the verdict itself rather than a variable it read.
    compliance["evidence"] = {"commands": []}

    # Parse all command results through their registered parsers
    processed_results = process_all_command_results(cmds_completed)

    # Process command lookups
    lookup_results = processed_results["lookup_command"]
    paths, builtins, missing, errors = process_command_lookups(
        lookup_results, process_effective_uid_results(cmds_completed)
    )

    # What each utility was looked for with, so a standard names the
    # lookup that decided a miss rather than a spelling of it
    lookups = {
        (result.get("args") or {}).get("cmd"): result.get("command")
        for result in lookup_results
    }

    # Only process getconf results if getconf is available
    if "getconf" in missing:
        # getconf is an XSI utility, so the loop below is what records
        # it as missing; naming it here too would name it twice
        compliance["xsi"]["supported"] = False

    else:
        cmd_type = "xsi_support"
        support_result = processed_results[cmd_type]
        parsed = support_result["parsed"]

        if parsed:
            compliance["xsi"].update(parsed)
            errors.extend(support_result.pop("errors", []))
        else:
            # busybox getconf exits nonzero for variables it does
            # not know, so an unanswerable probe is the platform
            # answering no
            compliance["xsi"]["supported"] = False

        # Either way the probe decided the verdict, so either way the
        # verdict names it; the variable is in the evidence only where
        # the host answered with one
        _record_probe(compliance["xsi"], support_result)

        for standard in ["xsh", "xcu", "xsi"]:
            cmd_type = f"{standard}_version"
            version_result = processed_results[cmd_type]
            parsed = version_result["parsed"]

            # Fallback: _POSIX2_VERSION may not exist on some
            # systems (e.g. Debian/glibc) since POSIX.2 was
            # merged into POSIX.1. Use _POSIX_VERSION instead.
            if not parsed and standard == "xcu":
                xsh_result = processed_results["xsh_version"]
                parsed = xsh_result["parsed"]
                if parsed:
                    version_result = xsh_result

            if parsed and compliance[standard].get("supported") is not False:
                compliance[standard].update(parsed)
                _record_probe(compliance[standard], version_result)
                errors.extend(version_result.pop("errors", []))

    for cmd in sorted(missing):
        if cmd in XCU_REQUIRED_COMMANDS:
            required_by = compliance["xcu"]
        elif cmd in XSI_REQUIRED_COMMANDS:
            required_by = compliance["xsi"]
        else:
            continue

        if required_by.get("supported") is True:
            required_by["supported"] = "partial"
        required_by["missing"].append(cmd)

        # The miss is the standard's own record, and the lookup that
        # missed is what put it there
        _name_command(required_by["evidence"], lookups.get(cmd))

    # POSIX requires both XSH (system interfaces) and XCU (shell/utilities)
    xsh_support = compliance["xsh"].get("supported")
    xcu_support = compliance["xcu"].get("supported")
    if xsh_support is True and xcu_support is True:
        compliance["posix"]["supported"] = True
    elif xsh_support is False and xcu_support is False:
        compliance["posix"]["supported"] = False
    elif xsh_support is not None and xcu_support is not None:
        compliance["posix"]["supported"] = "partial"

    _borrow_evidence(
        compliance["posix"], compliance["xsh"], compliance["xcu"]
    )

    # SUS requires full POSIX plus XSI extensions
    posix_support = compliance["posix"].get("supported")
    xsi_support = compliance["xsi"].get("supported")
    if posix_support is True and xsi_support is True:
        compliance["sus"]["supported"] = True
        # SUS version = XSI Issue - 3 (e.g., Issue 7 = SUSv4)
        xsi_issue = compliance["xsi"].get("version", {}).get("issue")
        if xsi_issue:
            xsi_issue = int(xsi_issue)
            sus_version = xsi_issue - 3
            compliance["sus"]["version"] = {
                "issue": xsi_issue,
                "id": sus_version,
                "pretty": f"v{sus_version}",
            }
    elif xsi_support in [True, "partial"]:
        compliance["sus"]["supported"] = "partial"
    else:
        compliance["sus"]["supported"] = False

    _borrow_evidence(
        compliance["sus"], compliance["posix"], compliance["xsi"]
    )

    # The one behavioral probe in a subsystem of declarations: the
    # sh test's verdict publishes beside the standards it evidences,
    # and the probe that produced it publishes beside the verdict
    sh_result = processed_results.get("sh_test")
    if sh_result is not None:
        parsed = sh_result["parsed"]
        if parsed:
            compliance.update(parsed)
            _name_command(compliance["evidence"], sh_result.get("command"))
        errors.extend(sh_result.pop("errors", []) or [])

    # The processor names its own facts, so the two producers that
    # share it cannot disagree about where they land.
    facts: dict[str, Any] = {
        "o0_os": {"compliance": compliance},
        "o0_paths": paths,
        # What enumerated the builtins is part of the shell's record,
        # so the sweep that asked names itself there
        "o0_shells": compose_shells(
            builtins={ANSWERING_SHELL: builtins},
            builtins_evidence=compose_evidence(
                commands=[LOOKUP_COMMAND]
            ),
        ),
    }

    return name_origins(facts, FQCN), errors
