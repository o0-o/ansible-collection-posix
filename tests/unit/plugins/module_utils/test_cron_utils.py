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

"""Unit tests for cron_utils module.

Four of the five corpora are live captures off running Linux, taken
from containers because the host this suite usually proves against has
no cron installed at all:

``crontab_etc_debian.txt`` is the ``/etc/crontab`` that
``docker.io/library/debian:stable`` ships once the ``cron`` package is
installed. ``crontab_etc_fedora.txt`` and ``crontab_cron_d_fedora.txt``
are ``registry.fedoraproject.org/fedora:latest``'s, with ``cronie``.
``crontab_user_cronie.txt`` is a per-user crontab installed into that
same image's real cronie spool and read back with ``crontab -l``.

``crontab_user_bsd.txt`` is written by hand in the form Vixie cron
writes on the BSDs and macOS, including the three header lines it
prepends and strips again, because no host of that family was in reach
to capture one from.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils.cron_utils import (
    CRON_KERNEL_DIALECTS,
    FREEBSD,
    OPENBSD,
    POSIX,
    VIXIE,
    cron_dialects,
    cron_job_lines,
    cron_kernel_name,
    cron_refusals,
    field_dialects,
    invalid_cron_jobs,
    parse_crontab,
    render_cron_job,
    schedule_dialects,
    schedule_refusal,
)

FILES = Path(__file__).parent / "files"

# Which corpora came off a running host and which were written from the
# documented form
LIVE = ("etc_debian", "etc_fedora", "cron_d_fedora", "user_cronie")
CONSTRUCTED = ("user_bsd",)

# The files whose rows name the user to run as. A system crontab and
# the files under /etc/cron.d are root's statement about what runs as
# whom; a per-user crontab sits in a spool that answers that already.
USER_COLUMN = {
    "etc_debian": True,
    "etc_fedora": True,
    "cron_d_fedora": True,
    "user_cronie": False,
    "user_bsd": False,
}


def corpus(name: str) -> str:
    """Read one crontab corpus.

    :param str name: The corpus suffix
    :returns str: The file's contents
    """
    return (FILES / f"crontab_{name}.txt").read_text()


def parsed(name: str) -> dict:
    """Parse one crontab corpus the way its file would be read.

    :param str name: The corpus suffix
    :returns dict: What the crontab configures
    """
    return parse_crontab(corpus(name), user_column=USER_COLUMN[name])


@pytest.mark.parametrize("name", LIVE + CONSTRUCTED)
def test_a_crontab_is_two_kinds_of_line(name: str) -> None:
    """Test every corpus reaches the same two-part shape.

    Some lines set a variable for every job below them and some are
    jobs. Both are configuration and neither is the other.
    """
    config = parsed(name)

    assert set(config) == {"environment", "jobs"}
    assert all(
        isinstance(value, str)
        for value in config["environment"].values()
    )
    assert all(
        "schedule" in job and "command" in job for job in config["jobs"]
    )


def test_a_system_crontab_names_who_each_job_runs_as() -> None:
    """Test the user column is read where the file has one."""
    jobs = parsed("etc_debian")["jobs"]

    assert len(jobs) == 4
    assert all(job["user"] == "root" for job in jobs)
    assert jobs[0]["schedule"] == {
        "minute": "17",
        "hour": "*",
        "day": "*",
        "month": "*",
        "weekday": "*",
    }


def test_a_command_keeps_the_shell_text_it_is() -> None:
    """Test a command is the rest of the line, whatever is in it.

    Debian's own crontab runs commands carrying ``&&``, ``||`` and a
    braced list with a semicolon in it, and none of that is a field
    separator once the schedule and the user have been read.
    """
    jobs = parsed("etc_debian")["jobs"]

    assert jobs[1]["command"] == (
        "test -x /usr/sbin/anacron || "
        "{ cd / && run-parts --report /etc/cron.daily; }"
    )
    assert parsed("user_bsd")["jobs"][2]["command"] == (
        "/usr/local/bin/heartbeat >/dev/null 2>&1"
    )


def test_a_per_user_crontab_names_no_user() -> None:
    """Test the spool answers whose crontab it is, so the row need not.

    A row here that named a user would be reporting the first word of
    the command as one.
    """
    jobs = parsed("user_cronie")["jobs"]

    assert all("user" not in job for job in jobs)
    assert jobs[2]["command"] == "/usr/bin/every-five"


def test_the_special_strings_are_a_form_and_not_a_fallback() -> None:
    """Test cron's named schedules are understood as themselves."""
    jobs = parsed("user_cronie")["jobs"]

    assert jobs[0]["schedule"] == {"special": "reboot"}
    assert jobs[0]["command"] == "/usr/local/bin/boot-job --flag"
    assert jobs[1]["schedule"] == {"special": "daily"}
    assert parsed("user_bsd")["jobs"][1]["schedule"] == {"special": "weekly"}


def test_a_schedule_is_kept_as_the_file_wrote_it() -> None:
    """Test every spelling cron takes survives as itself.

    A step, a range, a list and a name are all cron's own way of
    writing a schedule and none is more canonical than another, so
    what is published is what a reader would find in the file.
    """
    schedules = [job["schedule"] for job in parsed("user_cronie")["jobs"]]

    assert schedules[2]["minute"] == "*/5"
    assert schedules[3]["weekday"] == "1-5"
    assert schedules[4]["day"] == "1,15"
    assert schedules[5]["month"] == "jan,feb"
    assert schedules[5]["weekday"] == "mon"


def test_the_environment_a_crontab_sets_is_read_apart() -> None:
    """Test an assignment is not a job and does not become one."""
    config = parsed("cron_d_fedora")

    assert config["environment"] == {
        "SHELL": "/bin/bash",
        "PATH": "/sbin:/bin:/usr/sbin:/usr/bin",
        "MAILTO": "root",
    }
    assert len(config["jobs"]) == 1


def test_a_crontab_that_sets_and_runs_nothing_says_so() -> None:
    """Test a file of assignments and comments holds no jobs.

    Fedora's own /etc/crontab is exactly that, and an empty job list is
    the truthful reading of it.
    """
    config = parsed("etc_fedora")

    assert config["jobs"] == []
    assert config["environment"]["MAILTO"] == "root"


def test_a_quoted_value_is_the_value_inside_the_quotes() -> None:
    """Test the quotes are syntax, the way cron reads them.

    A value is quoted to keep whitespace cron would trim, so what a
    job sees is what is inside them.
    """
    environment = parsed("user_bsd")["environment"]

    assert environment["MAILTO"] == ""
    assert environment["HOME"] == "/home/operator"
    assert parse_crontab('FOO="  kept  "')["environment"]["FOO"] == (
        "  kept  "
    )


def test_an_assignment_inside_a_command_stays_in_the_command() -> None:
    """Test the identifier anchor tells an assignment from a job.

    No schedule's first field can be a name followed by an equals
    sign, because a minute is counted rather than called something.
    """
    config = parse_crontab("0 2 * * * FOO=bar /usr/bin/x")

    assert config["environment"] == {}
    assert config["jobs"][0]["command"] == "FOO=bar /usr/bin/x"


def test_comments_and_blank_lines_configure_nothing() -> None:
    """Test the lines a crontab ignores are ignored here too."""
    config = parse_crontab("# a comment\n\n   \n\t# indented\n")

    assert config == {"environment": {}, "jobs": []}


@pytest.mark.parametrize(
    "line",
    [
        "not a crontab line at all",
        "run the backup every day now",
        "0 2 * * /usr/bin/too-few",
        "30 4 * * *",
        "@nosuch /usr/bin/x",
        "@reboot",
        "FOO",
        "0 2 * * mon,notaday /usr/bin/x",
    ],
)
def test_a_line_this_does_not_understand_fails(line: str) -> None:
    """Test an unreadable line stops the parse rather than vanishing.

    A crontab quietly missing a job reads as a host that does not run
    it, which is a worse answer than no answer.
    """
    with pytest.raises(ValueError, match="neither a comment"):
        parse_crontab(line)


def test_five_words_are_not_a_schedule_by_being_five() -> None:
    """Test letters are only a schedule where cron spells one.

    A minute is never named, so a word in the first three fields is a
    command that landed where a schedule belongs. Without that, any
    sentence of five words and a tail parsed as a job.
    """
    with pytest.raises(ValueError):
        parse_crontab("not a crontab line at all")

    # And the two fields cron does name still take their names
    assert parse_crontab("0 0 * dec sun /usr/bin/x")["jobs"][0][
        "schedule"
    ] == {
        "minute": "0",
        "hour": "0",
        "day": "*",
        "month": "dec",
        "weekday": "sun",
    }


def test_the_bsd_spellings_are_forms_of_their_own() -> None:
    """Test the schedules the BSDs added parse as themselves.

    OpenBSD writes ~ random ranges into its own stock root crontab,
    so a parser refusing them fails a supported platform in factory
    state; FreeBSD names @every_minute and @every_second. Each is
    kept as the file wrote it, like every other spelling.
    """
    jobs = parsed("user_bsd")["jobs"]

    daily = [j for j in jobs if j["command"] == "/bin/sh /etc/daily"]
    assert daily[0]["schedule"]["minute"] == "30~45"
    assert daily[0]["schedule"]["hour"] == "1"

    weekly = [j for j in jobs if j["command"] == "/bin/sh /etc/weekly"]
    assert weekly[0]["schedule"]["minute"] == "~"
    assert weekly[0]["schedule"]["weekday"] == "6"

    named = sorted(
        j["schedule"]["special"]
        for j in jobs
        if "special" in j["schedule"] and j["schedule"]["special"] != "weekly"
    )
    assert named == ["every_minute", "every_second"]


# --- Whose spelling a schedule is written in ---------------------------


@pytest.mark.parametrize(
    "field, value",
    [
        ("minute", "*"),
        ("minute", "0"),
        ("hour", "10-11,22"),
        ("day", "1,15"),
        ("month", "12"),
        ("weekday", "0-6"),
    ],
)
def test_a_posix_spelling_is_a_number_a_range_a_list_or_a_star(
    field: str, value: str
) -> None:
    """Test the spellings the standard defines are filed as its own."""
    assert field_dialects(field, value) == {POSIX}


@pytest.mark.parametrize(
    "field, value, expected",
    [
        ("minute", "*/5", {VIXIE}),
        ("minute", "0-30/5", {POSIX, VIXIE}),
        ("minute", "*,5", {POSIX, VIXIE}),
        ("month", "jan,feb", {VIXIE}),
        ("weekday", "mon", {VIXIE}),
        ("weekday", "mon-fri", {VIXIE}),
        ("weekday", "MON", {VIXIE}),
        ("weekday", "7", {VIXIE}),
        ("weekday", "0-7", {POSIX, VIXIE}),
    ],
)
def test_a_vixie_spelling_is_a_step_a_name_or_a_seventh_day(
    field: str, value: str, expected: set
) -> None:
    """Test Vixie's extensions are filed as Vixie's.

    A star inside a list and a weekday of 7 are Vixie's readings too,
    though neither looks like an extension: POSIX spells every value
    as a star that is the whole field, and counts the week 0 to 6.
    """
    assert field_dialects(field, value) == expected


@pytest.mark.parametrize(
    "field, value, expected",
    [
        ("minute", "~", {OPENBSD}),
        ("minute", "30~45", {OPENBSD, POSIX}),
        ("minute", "~30", {OPENBSD, POSIX}),
        ("minute", "30~", {OPENBSD, POSIX}),
        ("minute", "30~45/5", {OPENBSD, POSIX, VIXIE}),
    ],
)
def test_the_openbsd_spelling_is_a_tilde(
    field: str, value: str, expected: set
) -> None:
    """Test the random-value forms are filed as OpenBSD's."""
    assert field_dialects(field, value) == expected


def test_the_special_strings_have_owners() -> None:
    """Test the eight are Vixie's and the two are FreeBSD's."""
    assert schedule_dialects({"special": "reboot"}) == {VIXIE}
    assert schedule_dialects({"special": "midnight"}) == {VIXIE}
    assert schedule_dialects({"special": "every_minute"}) == {FREEBSD}
    assert schedule_dialects({"special": "every_second"}) == {FREEBSD}


@pytest.mark.parametrize(
    "field, value",
    [
        ("minute", "60"),
        ("hour", "24"),
        ("day", "0"),
        ("day", "32"),
        ("month", "13"),
        ("weekday", "8"),
        ("weekday", "monday"),
        ("minute", "jan"),
        ("minute", "*/0"),
        ("minute", "1,,2"),
        ("minute", "5-"),
        ("minute", "-5"),
        ("minute", ""),
        ("minute", None),
        ("second", "0"),
    ],
)
def test_a_spelling_no_cron_takes_is_nobodys(field: str, value) -> None:
    """Test a number out of range or a name in the wrong field is None.

    None is not a dialect: it is the answer that no cron at all reads
    the field, which is a different thing from a spelling this host's
    cron does not take.
    """
    assert field_dialects(field, value) is None


@pytest.mark.parametrize(
    "schedule",
    [
        {"special": "nosuch"},
        {"special": "reboot", "minute": "0"},
        {"minute": "0", "hour": "0"},
        {"minute": "0", "hour": "0", "day": "*", "month": "*",
         "weekday": "*", "second": "0"},
        "0 0 * * *",
        None,
    ],
)
def test_a_schedule_that_is_not_one_is_nobodys(schedule) -> None:
    """Test the shape is checked before the spelling."""
    assert schedule_dialects(schedule) is None


def test_a_schedule_draws_on_every_owner_it_uses() -> None:
    """Test the set names each dialect a schedule leans on."""
    assert schedule_dialects(
        {
            "minute": "~",
            "hour": "*/2",
            "day": "*",
            "month": "*",
            "weekday": "mon",
        }
    ) == {OPENBSD, POSIX, VIXIE}
    assert schedule_dialects(
        {"minute": "0", "hour": "0", "day": "*", "month": "*", "weekday": "*"}
    ) == {POSIX}


# --- What each kernel's cron takes ---------------------------------------


@pytest.mark.parametrize(
    "kernel, expected",
    [
        ("Linux", {POSIX, VIXIE}),
        ("linux", {POSIX, VIXIE}),
        ("Darwin", {POSIX, VIXIE}),
        ("NetBSD", {POSIX, VIXIE}),
        ("FreeBSD", {POSIX, VIXIE, FREEBSD}),
        ("OpenBSD", {POSIX, VIXIE, OPENBSD}),
    ],
)
def test_a_kernel_names_what_its_cron_takes(kernel: str, expected) -> None:
    """Test the kernel is folded and looked up the way o0_os names it.

    Every supported kernel runs a Vixie-descended cron; the two that
    extended it take their own spellings and nobody else's.
    """
    assert cron_dialects(kernel) == expected


@pytest.mark.parametrize("kernel", ["SunOS", "GNU", "", "  ", None, 7])
def test_a_kernel_this_does_not_know_gets_no_verdict(kernel) -> None:
    """Test an unknown kernel is None, which is no verdict at all."""
    assert cron_dialects(kernel) is None


def test_linux_is_held_to_the_family_and_no_further() -> None:
    """Test Linux does not warn on any Vixie spelling.

    cronie, Debian's cron and busybox's are all the Vixie family or a
    subset of it, and the kernel does not say which, so a spelling
    inside the family is never Linux's to refuse.
    """
    assert CRON_KERNEL_DIALECTS["linux"] == {POSIX, VIXIE}
    assert (
        invalid_cron_jobs(parsed("user_cronie"), cron_dialects("Linux")) == []
    )


# --- What a host's cron would refuse -------------------------------------


@pytest.mark.parametrize("name", LIVE)
@pytest.mark.parametrize("kernel", sorted(CRON_KERNEL_DIALECTS))
def test_every_live_corpus_is_taken_by_every_known_cron(
    name: str, kernel: str
) -> None:
    """Test the stock files hold nothing any supported cron refuses."""
    assert invalid_cron_jobs(parsed(name), cron_dialects(kernel)) == []


@pytest.mark.parametrize(
    "kernel, refused",
    [
        ("Linux", ["30~45", "~", "@every_minute", "@every_second"]),
        ("Darwin", ["30~45", "~", "@every_minute", "@every_second"]),
        ("NetBSD", ["30~45", "~", "@every_minute", "@every_second"]),
        ("FreeBSD", ["30~45", "~"]),
        ("OpenBSD", ["@every_minute", "@every_second"]),
    ],
)
def test_the_bsd_corpus_is_held_to_each_kernel(
    kernel: str, refused: list
) -> None:
    """Test each kernel refuses the other BSD's spellings and not its own."""
    found = invalid_cron_jobs(parsed("user_bsd"), cron_dialects(kernel))

    assert [f["spelling"] for f in found] == refused
    assert all(f["dialect"] in (OPENBSD, FREEBSD) for f in found)
    # And each refusal carries the job it is about, in file order
    assert [f["index"] for f in found] == sorted(f["index"] for f in found)
    assert all(f["job"]["schedule"] is not None for f in found)


def test_cron_stops_at_the_first_field_it_cannot_read() -> None:
    """Test a refusal names one field, the first, the way cron does."""
    refusal = schedule_refusal(
        {
            "minute": "~",
            "hour": "24",
            "day": "*",
            "month": "*",
            "weekday": "*",
        },
        cron_dialects("Linux"),
    )

    assert refusal == {"field": "minute", "spelling": "~", "dialect": OPENBSD}

    nobodys = schedule_refusal(
        {
            "minute": "0",
            "hour": "24",
            "day": "*",
            "month": "*",
            "weekday": "*",
        },
        cron_dialects("Linux"),
    )
    assert nobodys == {"field": "hour", "spelling": "24", "dialect": None}

    assert schedule_refusal({"special": "nosuch"}, cron_dialects("Linux")) == {
        "field": "special",
        "spelling": "@nosuch",
        "dialect": None,
    }
    assert (
        schedule_refusal({"special": "reboot"}, cron_dialects("Linux")) is None
    )


def test_a_config_that_is_not_one_refuses_nothing() -> None:
    """Test the lib surface is safe to hand a fact of any shape."""
    dialects = cron_dialects("Linux")

    assert invalid_cron_jobs(None, dialects) == []
    assert invalid_cron_jobs({"jobs": "not a list"}, dialects) == []
    assert invalid_cron_jobs({"jobs": [None, "x"]}, dialects) == []


# --- Naming the kernel, the line and the spelling ------------------------


@pytest.mark.parametrize(
    "variables, expected",
    [
        ({"ansible_facts": {"o0_os": {"kernel": {"name": "linux"}}}}, "linux"),
        ({"o0_os": {"kernel": {"name": "darwin"}}}, "darwin"),
        ({"ansible_system": "FreeBSD"}, "freebsd"),
        ({"ansible_facts": {"system": "OpenBSD"}}, "openbsd"),
        # o0_os is preferred over the setup module's word for it
        (
            {"o0_os": {"kernel": {"name": "linux"}}, "ansible_system": "X"},
            "linux",
        ),
        ({"o0_os": {"kernel": {"pretty": "Linux"}}}, None),
        ({"o0_os": "not a mapping"}, None),
        ({}, None),
        (None, None),
    ],
)
def test_a_variable_namespace_names_its_kernel(variables, expected) -> None:
    """Test the kernel is read from where a play would have put it.

    o0_os.kernel.name first, under ansible_facts and injected at the
    top; ansible_system where no o0_o gather has run; nothing else,
    because a distribution is not a kernel.
    """
    assert cron_kernel_name(variables) == expected


@pytest.mark.parametrize("name", LIVE + CONSTRUCTED)
def test_the_job_lines_line_up_with_the_parsed_jobs(name: str) -> None:
    """Test every job can be named by the line it came from."""
    lines = cron_job_lines(corpus(name), user_column=USER_COLUMN[name])

    assert len(lines) == len(parsed(name)["jobs"])
    assert lines == sorted(lines)


def test_the_bsd_corpus_job_lines_are_the_files() -> None:
    """Test the numbers are the file's, comments and blanks counted."""
    assert cron_job_lines(corpus("user_bsd")) == [10, 11, 12, 16, 17, 20, 21]


def test_a_refusal_names_the_crontab_the_line_and_the_spelling() -> None:
    """Test a warning is one edit away from the fix.

    It names the crontab as the caller labels it, the line by the
    file's numbering, the field and the spelling, whose spelling it is
    and whose cron refuses it, and quotes the line as written.
    """
    text = corpus("user_bsd")
    warned = cron_refusals(
        parse_crontab(text), "linux", "uid 501's crontab", content=text
    )

    assert len(warned) == 4
    assert warned[0] == (
        "uid 501's crontab line 16: minute '30~45' is an OpenBSD spelling"
        " and linux's cron does not take it, so the job will not run:"
        " 30~45\t1\t*\t*\t*\t/bin/sh /etc/daily"
    )
    assert warned[3] == (
        "uid 501's crontab line 21: '@every_second' is a FreeBSD spelling"
        " and linux's cron does not take it, so the job will not run:"
        " @every_second /usr/local/bin/tick"
    )


def test_a_refusal_without_the_file_names_the_job_and_renders_it() -> None:
    """Test a job read back out of a fact is still named and quoted."""
    config = parse_crontab(
        "~ 2 * * 6 root /bin/sh /etc/weekly", user_column=True
    )
    warned = cron_refusals(config, "linux", "/etc/cron.d/random")

    assert warned == [
        "/etc/cron.d/random job 1: minute '~' is an OpenBSD spelling and"
        " linux's cron does not take it, so the job will not run:"
        " ~ 2 * * 6 root /bin/sh /etc/weekly"
    ]


@pytest.mark.parametrize("kernel", ["SunOS", None])
def test_an_unknown_kernel_earns_no_warning(kernel) -> None:
    """Test no verdict is given where none can be."""
    assert cron_refusals(parsed("user_bsd"), kernel, "x") == []


def test_a_job_is_rendered_as_the_line_it_would_be() -> None:
    """Test the rendering has the same words in the same order."""
    assert render_cron_job(
        {"schedule": {"special": "reboot"}, "user": "root", "command": "/x"}
    ) == "@reboot root /x"
    assert render_cron_job(
        {
            "schedule": {
                "minute": "~",
                "hour": "2",
                "day": "*",
                "month": "*",
                "weekday": "6",
            },
            "command": "/bin/sh /etc/weekly",
        }
    ) == "~ 2 * * 6 /bin/sh /etc/weekly"
