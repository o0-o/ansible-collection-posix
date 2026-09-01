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

"""Unit tests for compliance_utils module_utils."""

from __future__ import annotations

from typing import Any, Optional

from ansible_collections.o0_o.posix.plugins.module_utils.compliance_utils import (  # noqa: E501
    POSIX_OPTIONAL_UTILITIES,
    POSIX_UTILITIES,
    SUS,
    POSIX,
    XCU_REQUIRED_COMMANDS,
    XCU_REQUIRED_UTILITIES,
    XCU_RESERVED_WORDS,
    XCU_SPECIAL_BUILTINS,
    XSH,
    XCU,
    XSI,
    XSI_REQUIRED_COMMANDS,
    get_compliance_command_requests,
    missing_commands,
    process_all_compliance_command_results,
)

# What the fabricated host answers for each getconf probe
GETCONF_ANSWERS = {
    "_POSIX_VERSION": "200809",
    "_POSIX2_VERSION": "200809",
    "_XOPEN_UNIX": "1",
    "_XOPEN_VERSION": "700",
}

# Everything else it has as a path; these it answers otherwise
BUILTIN_COMMANDS = {".", ":", "[", "cd", "exec"}
ALIASED_COMMANDS = {"ls": "ls --color=auto"}
# What the fabricated host lacks. ipcs is an XSI utility, so the host
# is a conformant POSIX system that does not claim the XSI option in
# full - which is what lets the tests below read the base standards as
# clean while one option group is partial.
MISSING_COMMANDS = {"ipcs"}

# Whose answers the sweep's lookups are. command -v names a pathname
# the shell running it would run, so the claim is keyed by the uid
# that shell was running as
EFFECTIVE_UID = 1000

# The module whose sweep composed these entries. A gather that runs
# the sweep adds its own name beside this one.
COMPOSED_BY = "o0_o.posix.compliance"
RESOLVED = {
    "executable": {str(EFFECTIVE_UID): True},
    "evidence": {"commands": ["command"]},
    "origins": [COMPOSED_BY],
}


def _answer(
    request: dict[str, Any],
    missing: Optional[set[str]] = None,
) -> dict[str, Any]:
    """Answer one compliance request the way the run plugin does.

    The run plugin merges each request dict with the return code and
    output of the command it names, so a fabricated answer is the
    request plus those keys.

    :param dict[str, Any] request: A compliance command request
    :param Optional[set[str]] missing: What this host lacks, for a
        test that needs a different gap than the default one
    :returns dict[str, Any]: The request merged with its result
    """
    lacking = MISSING_COMMANDS if missing is None else missing

    if request["type"] == "lookup_command":
        cmd = request["args"]["cmd"]
        if cmd in lacking:
            return dict(
                request,
                rc=1,
                stdout="",
                stdout_lines=[],
                stderr="",
                stderr_lines=[],
            )
        if cmd in ALIASED_COMMANDS:
            stdout = f"alias {cmd}='{ALIASED_COMMANDS[cmd]}'"
        elif cmd in BUILTIN_COMMANDS:
            stdout = cmd
        else:
            stdout = f"/usr/bin/{cmd}"
    elif request["type"] == "sh_test":
        stdout = "posix sh"
    elif request["type"] == "effective_uid":
        stdout = str(EFFECTIVE_UID)
    else:
        stdout = GETCONF_ANSWERS[request["command"][1]]

    return dict(
        request,
        rc=0,
        stdout=stdout,
        stdout_lines=[stdout],
        stderr="",
        stderr_lines=[],
    )


def _process_fabricated_host(
    missing: Optional[set[str]] = None,
) -> dict[str, Any]:
    """Run every compliance request through the shared processor.

    :param Optional[set[str]] missing: What this host lacks
    :returns dict[str, Any]: The facts the processor publishes
    """
    results = [
        _answer(r, missing) for r in get_compliance_command_requests()
    ]
    facts, errors = process_all_compliance_command_results(results)
    assert errors == []
    return facts


class TestConstants:
    """Tests for standard metadata constants."""

    def test_sus_metadata(self) -> None:
        """Test SUS constant has required fields."""
        assert SUS["name"] == "Single UNIX Specification"
        assert SUS["abbreviation"] == "SUS"
        assert "description" in SUS

    def test_posix_metadata(self) -> None:
        """Test POSIX constant has required fields."""
        assert POSIX["name"] == "Portable Operating System Interface"
        assert POSIX["abbreviation"] == "POSIX"
        assert "description" in POSIX

    def test_xsh_metadata(self) -> None:
        """Test XSH constant has required fields."""
        assert XSH["abbreviation"] == "XSH"
        assert "name" in XSH

    def test_xcu_metadata(self) -> None:
        """Test XCU constant has required fields."""
        assert XCU["abbreviation"] == "XCU"
        assert "name" in XCU

    def test_xsi_metadata(self) -> None:
        """Test XSI constant has required fields."""
        assert XSI["abbreviation"] == "XSI"
        assert "name" in XSI


class TestProcessAllComplianceCommandResults:
    """Tests for the facts the shared compliance processor names."""

    def test_every_namespace_is_prefixed(self) -> None:
        """Test the processor publishes o0_ namespaces only, so the
        facts aggregator merging its return cannot leak a bare key."""
        facts = _process_fabricated_host()

        assert set(facts) == {"o0_os", "o0_paths", "o0_shells"}
        assert all(ns.startswith("o0_") for ns in facts)

    def test_compliance_under_o0_os(self) -> None:
        """Test compliance lands where the standalone action has
        published it since 2026-01-13."""
        facts = _process_fabricated_host()

        compliance = facts["o0_os"]["compliance"]
        assert compliance["posix"]["supported"] is True
        assert compliance["xsh"]["version"]["name"] == "POSIX.1-2008"
        assert compliance["xsi"]["version"]["issue"] == 7

    def test_sh_posix_compliant_published(self) -> None:
        """The sh test's behavioral verdict lands beside the standards."""
        facts = _process_fabricated_host()
        compliance = facts["o0_os"]["compliance"]
        assert compliance["sh_posix_compliant"] is True

    def test_a_resolved_command_files_under_its_path(self) -> None:
        """Test a command the sweep found is a fact about the file it
        found, recorded as executable because the shell named it as a
        pathname it would run."""
        facts = _process_fabricated_host()

        assert facts["o0_paths"]["/usr/bin/awk"] == RESOLVED

    def test_builtins_file_on_the_shell_and_not_on_a_path(self) -> None:
        """Test a builtin is a fact about the shell binary.

        It resolves to no file, so there is no path for it to be a
        fact about, and no home changes which commands a shell is
        built out of - so it sits at the shell in o0_shells rather
        than in one of the per-home rows or in the path store.
        """
        facts = _process_fabricated_host()

        assert facts["o0_shells"]["/bin/sh"]["builtins"] == sorted(
            BUILTIN_COMMANDS
        )
        assert "builtins" not in facts["o0_paths"]["/bin/sh"]

    def test_an_alias_lands_in_neither(self) -> None:
        """Test an alias is not the sweep's to report.

        It comes out of a rc file, so it belongs to a shell and a home
        together, and the shell-context probe is what reports it into
        that row's config.
        """
        facts = _process_fabricated_host()

        assert "aliases" not in facts["o0_paths"]["/bin/sh"]
        assert "aliases" not in facts["o0_shells"]["/bin/sh"]

    def test_a_missing_command_files_null_at_each_candidate(self) -> None:
        """Test a miss is confirmed absence at the paths it was looked
        for, which are the directories the sweep's own resolutions
        name, rather than a list of names kept somewhere else."""
        facts = _process_fabricated_host()

        for cmd in MISSING_COMMANDS:
            assert facts["o0_paths"][f"/usr/bin/{cmd}"] is None

    def test_each_path_carries_one_whole_observation(self) -> None:
        """Test the shell that answered and the file sh resolved to are
        two paths with two observations, neither of them a fragment the
        other has to be blended with. The store replaces an entry
        whole, so a producer that filed half of one would lose the
        other half to the next producer along."""
        facts = _process_fabricated_host()

        assert facts["o0_paths"]["/usr/bin/sh"] == RESOLVED
        # The shell ran the probes, so it is not one of the misses;
        # nothing was learned about the file itself, so the entry
        # says exactly that
        assert facts["o0_paths"]["/bin/sh"] == {
            "evidence": {"commands": ["command"]},
            "origins": [COMPOSED_BY],
        }

    def test_the_missing_list_derives_from_the_standards(self) -> None:
        """Test the commands a host lacks are read back out of the
        standards that require them, so nothing has to store them a
        second time."""
        facts = _process_fabricated_host()

        assert missing_commands(facts["o0_os"]["compliance"]) == sorted(
            MISSING_COMMANDS
        )

    def test_a_missing_command_downgrades_its_standard(self) -> None:
        """Test a missing XSI command is recorded beside the standard's
        verdict and turns full support into partial."""
        facts = _process_fabricated_host()

        xsi = facts["o0_os"]["compliance"]["xsi"]
        assert xsi["supported"] == "partial"
        assert xsi["missing"] == sorted(MISSING_COMMANDS)

    def test_a_missing_base_utility_downgrades_the_base(self) -> None:
        """Test a gap in the mandatory base is named as one.

        Which standard a miss lands under is the whole point of
        keeping the two lists right. pax is a mandatory base utility,
        so a host without it is not a conformant POSIX system - and
        while pax sat in the XSI list, such a host read as fully
        conformant with one optional extension missing.
        """
        facts = _process_fabricated_host(missing={"pax"})
        compliance = facts["o0_os"]["compliance"]

        assert compliance["xcu"]["missing"] == ["pax"]
        assert compliance["xcu"]["supported"] == "partial"
        assert compliance["posix"]["supported"] == "partial"
        assert compliance["xsi"]["missing"] == []

    def test_every_probe_names_what_it_read(self) -> None:
        """Test a probe adds to what the earlier probes left rather
        than replacing it, so the _XOPEN_UNIX answer that decided XSI
        support survives the _XOPEN_VERSION one that dated it. The
        value is typed the way o0_os.config types it, because the two
        are one fact read at two moments."""
        compliance = _process_fabricated_host()["o0_os"]["compliance"]

        assert compliance["xsi"]["evidence"]["config"] == {
            "_XOPEN_UNIX": 1,
            "_XOPEN_VERSION": 700,
        }
        assert compliance["xsh"]["evidence"]["config"] == {
            "_POSIX_VERSION": 200809,
        }
        assert compliance["xcu"]["evidence"]["config"] == {
            "_POSIX2_VERSION": 200809,
        }

    def test_every_probe_names_the_command_it_consulted(self) -> None:
        """Test a standard names the commands that decided it, and
        names them rather than spelling them out: XSI is asked for two
        variables and looks for four utilities, and one name answers
        for every invocation of one command."""
        compliance = _process_fabricated_host()["o0_os"]["compliance"]

        assert compliance["xsh"]["evidence"]["commands"] == ["getconf"]
        assert compliance["xsi"]["evidence"]["commands"] == [
            "command",
            "getconf",
        ]
        # XCU found every utility it requires, so nothing but the
        # version probe decided it
        assert compliance["xcu"]["evidence"]["commands"] == ["getconf"]

    def test_a_derived_standard_borrows_what_derives_it(self) -> None:
        """Test POSIX and SUS, which probe nothing of their own, name
        the evidence of the standards they are composed of, so a
        consumer reads a verdict and its support together without
        knowing which standards add up to it."""
        compliance = _process_fabricated_host()["o0_os"]["compliance"]

        assert compliance["posix"]["evidence"] == {
            "commands": ["getconf"],
            "config": {"_POSIX_VERSION": 200809, "_POSIX2_VERSION": 200809},
        }
        assert compliance["sus"]["evidence"] == {
            "commands": ["command", "getconf"],
            "config": {
                "_POSIX_VERSION": 200809,
                "_POSIX2_VERSION": 200809,
                "_XOPEN_UNIX": 1,
                "_XOPEN_VERSION": 700,
            },
        }

    def test_the_sh_verdict_names_its_probe(self) -> None:
        """Test the namespace's own verdict names the probe that
        produced it beside itself, as a command and nothing else: the
        probe's answer is the published verdict rather than a
        configuration variable it read."""
        compliance = _process_fabricated_host()["o0_os"]["compliance"]

        assert compliance["evidence"] == {"commands": ["sh"]}

    def test_the_missing_list_outlives_the_probes(self) -> None:
        """Test the missing list seeded for the standards that require
        utilities is still there once the getconf probes are in, so a
        standard that found all of its own says so with an empty list
        rather than with silence."""
        compliance = _process_fabricated_host()["o0_os"]["compliance"]

        assert compliance["xcu"]["missing"] == []
        assert set(compliance["xsi"]) == {
            "name",
            "abbreviation",
            "description",
            "supported",
            "version",
            "missing",
            "evidence",
            "origins",
        }

    def test_a_standard_names_only_the_kinds_it_attempts(self) -> None:
        """Test evidence is kind by key: compliance reads no files, so
        no record carries the files kind at all, while the two kinds it
        does attempt are present even where they decided nothing."""
        compliance = _process_fabricated_host()["o0_os"]["compliance"]

        for standard in ("xsh", "xcu", "xsi", "posix", "sus"):
            evidence = compliance[standard]["evidence"]
            assert set(evidence) == {"commands", "config"}
            assert all(
                isinstance(name, str) for name in evidence["commands"]
            )
            assert evidence["commands"] == sorted(set(evidence["commands"]))


class TestOriginsNameTheSweep:
    """Tests for who the compliance sweep says composed its facts."""

    def test_every_standard_names_the_sweep(self) -> None:
        """Test a verdict names who decided it as well as what did.

        Origins sits where evidence sits, and each standard carries
        its own evidence because the standards are decided by
        different probes, so each carries its own origins too.
        """
        facts = _process_fabricated_host()
        compliance = facts["o0_os"]["compliance"]

        for standard in ("xsh", "xcu", "xsi", "posix", "sus"):
            assert compliance[standard]["origins"] == [COMPOSED_BY]

    def test_the_namespace_verdict_names_the_sweep(self) -> None:
        """Test the sh probe's own verdict names its producer too."""
        compliance = _process_fabricated_host()["o0_os"]["compliance"]

        assert compliance["origins"] == [COMPOSED_BY]

    def test_a_standard_field_is_not_a_composition_of_its_own(self) -> None:
        """Test a version or a missing list claims no producer.

        Only a mapping that says what was consulted is a composition
        with a producer to name.
        """
        compliance = _process_fabricated_host()["o0_os"]["compliance"]

        assert "origins" not in compliance["xsh"]["version"]
        assert "origins" not in compliance["xsi"]["evidence"]


# ---------------------------------------------------------------------
# What the conformance lists are allowed to contain
# ---------------------------------------------------------------------


def test_the_index_is_the_standard_s_own() -> None:
    """Test the utility index is the whole of what POSIX defines.

    It is the authority every other list here is held to, so its size
    is pinned: a name that falls out of it silently would take a
    conformance claim with it.
    """
    assert len(POSIX_UTILITIES) == 160
    for utility in ("awk", "pax", "crontab", "at", "batch", "getconf"):
        assert utility in POSIX_UTILITIES


def test_a_required_utility_is_one_the_standard_names() -> None:
    """Test nothing is required that POSIX never asked for.

    This is the guard against the defect that put tar in the list: a
    utility the standard does not define cannot be a conformance
    requirement, however common it is.
    """
    # [ is documented on the test page rather than indexed separately
    named = XCU_REQUIRED_UTILITIES - {"["}

    assert named <= POSIX_UTILITIES
    assert XSI_REQUIRED_COMMANDS <= POSIX_UTILITIES


def test_tar_is_not_a_posix_utility() -> None:
    """Test the archiver POSIX names is pax and tar is not required.

    tar was dropped from the standard in POSIX.1-2001 and pax took its
    place. A conformant host without tar was reading as non-conformant.
    """
    assert "tar" not in POSIX_UTILITIES
    assert "tar" not in XCU_REQUIRED_COMMANDS
    assert "pax" in XCU_REQUIRED_UTILITIES


def test_stat_is_not_a_posix_utility_either() -> None:
    """Test the other common-but-not-standard name is gone too.

    stat is on every host anybody runs and is not in the standard, so
    requiring it asserted something POSIX never did.
    """
    assert "stat" not in POSIX_UTILITIES
    assert "stat" not in XCU_REQUIRED_COMMANDS


def test_nothing_optional_is_required_of_every_host() -> None:
    """Test an option group's utilities are not demanded of the base.

    A conformant system need not ship SCCS, FORTRAN or the batch
    utilities, and macOS - a certified UNIX - ships none of them.
    """
    assert not (XCU_REQUIRED_UTILITIES & POSIX_OPTIONAL_UTILITIES)
    for optional in ("sccs", "fort77", "qsub", "make", "vi", "uucp"):
        assert optional in POSIX_OPTIONAL_UTILITIES
        assert optional not in XCU_REQUIRED_COMMANDS


def test_the_scheduling_utilities_are_required_of_every_host() -> None:
    """Test at, batch and crontab are base rather than optional.

    Their synopses carry no option marker, so a host without them is
    not conformant - and the sweep that did not ask about them let a
    host with no cron at all read as clean.
    """
    for utility in ("at", "batch", "crontab"):
        assert utility in XCU_REQUIRED_UTILITIES
        assert utility not in XSI_REQUIRED_COMMANDS


def test_the_xsi_list_is_what_the_xsi_marker_covers() -> None:
    """Test XSI requires the utilities marked XSI and no others.

    getconf and pax were here and are mandatory base utilities, so a
    host lacking one has an XCU gap; reading it as an XSI gap named
    the wrong standard for a real defect.
    """
    for utility in ("fuser", "ipcrm", "ipcs", "link", "unlink", "sccs"):
        assert utility in XSI_REQUIRED_COMMANDS

    assert "getconf" not in XSI_REQUIRED_COMMANDS
    assert "pax" not in XSI_REQUIRED_COMMANDS
    # Every one of them is an option-group utility rather than a
    # mandatory one, which is what makes it XSI's to require
    assert XSI_REQUIRED_COMMANDS <= POSIX_OPTIONAL_UTILITIES


def test_every_utility_the_standard_names_is_accounted_for() -> None:
    """Test the partition is total, which is what makes it complete.

    Every utility POSIX defines is either required of every host or
    belongs to an option group, and none is both. A utility that fell
    out of both lists would be one nothing here has an opinion about,
    which is how a list becomes a sample again.
    """
    # [ is documented on the test page rather than indexed separately
    named = XCU_REQUIRED_UTILITIES - {"["}

    assert named | POSIX_OPTIONAL_UTILITIES == POSIX_UTILITIES
    assert not (named & POSIX_OPTIONAL_UTILITIES)


def test_the_base_is_the_whole_base() -> None:
    """Test the mandatory set is the size the standard makes it.

    104 of the 160 utilities carry no option marker over their own
    name. Pinning the count is what catches a utility quietly leaving
    the required list, which under-reports a gap rather than
    announcing itself.
    """
    assert len(XCU_REQUIRED_UTILITIES - {"["}) == 104
    assert len(POSIX_OPTIONAL_UTILITIES) == 56


def test_the_option_groups_are_the_standard_s_own() -> None:
    """Test each optional group is there, by a member of each.

    The groups are User Portability, Software Development, C-language
    Development, UUCP, FORTRAN and the Batch Environment, plus XSI.
    """
    for utility in (
        "vi",  # User Portability
        "make",  # Software Development
        "c99",  # C-language Development
        "uucp",  # UUCP
        "asa",  # FORTRAN Runtime
        "fort77",  # FORTRAN Development
        "qsub",  # Batch Environment Services
        "ipcs",  # X/Open System Interfaces
    ):
        assert utility in POSIX_OPTIONAL_UTILITIES
        assert utility not in XCU_REQUIRED_COMMANDS


def test_the_two_lists_do_not_overlap() -> None:
    """Test a utility is required by one standard or the other.

    A command the host does not have is recorded once, in the list of
    the standard that requires it, so an overlap would name it twice.
    """
    assert not (XCU_REQUIRED_COMMANDS & XSI_REQUIRED_COMMANDS)


def test_the_shell_s_own_words_are_asked_about_as_what_they_are(
) -> None:
    """Test grammar and built-ins are kept apart from utilities.

    A special built-in is a command no PATH search finds and a
    reserved word is not a command at all, so neither is held to the
    utility index - and command -v answers for both, which is why the
    sweep works on them.
    """
    assert "export" in XCU_SPECIAL_BUILTINS
    assert "while" in XCU_RESERVED_WORDS
    assert not (XCU_SPECIAL_BUILTINS & POSIX_UTILITIES)
    assert not (XCU_RESERVED_WORDS & XCU_REQUIRED_UTILITIES)
    # And all of them are still swept for
    assert XCU_SPECIAL_BUILTINS <= XCU_REQUIRED_COMMANDS
    assert XCU_RESERVED_WORDS <= XCU_REQUIRED_COMMANDS


def test_both_lists_are_nonempty_and_the_sweep_asks_for_all_of_them(
) -> None:
    """Test every required command is actually looked up."""
    assert XCU_REQUIRED_COMMANDS
    assert XSI_REQUIRED_COMMANDS

    asked = {
        request["args"]["cmd"]
        for request in get_compliance_command_requests()
        if request.get("type") == "lookup_command"
    }

    assert XCU_REQUIRED_COMMANDS <= asked
    assert XSI_REQUIRED_COMMANDS <= asked
