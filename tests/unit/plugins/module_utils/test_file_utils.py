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

"""Unit tests for file_utils module."""

from __future__ import annotations

from typing import Any, Optional

from ansible_collections.o0_o.posix.plugins.module_utils.file_utils import (
    get_file_command_requests,
    process_file_command_results,
)


def _answered(
    requests: list[dict[str, Any]],
    files: dict[str, Optional[str]],
) -> list[dict[str, Any]]:
    """Answer requests the way the run plugin answers them.

    :param list[dict[str, Any]] requests: The requests to answer
    :param dict[str, Optional[str]] files: Content per path, None
        where the file is not there
    :returns list[dict[str, Any]]: The requests, answered
    """
    answered = []
    for request in requests:
        content = files.get(request["args"]["path"])
        if content is None:
            answered.append(
                {
                    **request,
                    "rc": 1,
                    "stdout": "",
                    "stderr": "cat: no such file",
                }
            )
        else:
            answered.append(
                {**request, "rc": 0, "stdout": content, "stderr": ""}
            )
    return answered


def test_one_request_per_path() -> None:
    """Test each path is a request of its own, so the reads travel in
    the batch rather than in round trips of their own."""
    requests = get_file_command_requests(["/etc/fstab", "/etc/shells"])

    assert [request["command"] for request in requests] == [
        ("cat", "/etc/fstab"),
        ("cat", "/etc/shells"),
    ]
    assert all(request["type"] == "file" for request in requests)


def test_no_paths_is_no_requests() -> None:
    """Test a producer with nothing to read adds nothing to the
    batch."""
    assert get_file_command_requests([]) == []


def test_results_are_keyed_by_the_path_each_one_read() -> None:
    """Test a batch of reads comes back apart, keyed by path, however
    many other commands rode with them."""
    files = {"/etc/fstab": "/dev/sd0a / ffs rw 1 1\n", "/etc/shells": None}
    requests = get_file_command_requests(list(files))

    results = process_file_command_results(_answered(requests, files))

    assert set(results) == {"/etc/fstab", "/etc/shells"}
    assert results["/etc/fstab"]["parsed"] == "/dev/sd0a / ffs rw 1 1\n"


def test_a_file_that_did_not_answer_reads_null() -> None:
    """Test a failed read is null rather than empty, and says why. A
    file that could not be read and a file that holds nothing are two
    answers, and the store keeps them apart."""
    files: dict[str, Optional[str]] = {"/etc/fstab": None}
    requests = get_file_command_requests(list(files))

    result = process_file_command_results(_answered(requests, files))

    assert result["/etc/fstab"]["parsed"] is None
    assert "no such file" in result["/etc/fstab"]["stderr"]


def test_an_empty_file_reads_empty() -> None:
    """Test a file that exists and holds nothing reads as the empty
    string it is, not as a file that did not answer."""
    files = {"/etc/shells": ""}
    requests = get_file_command_requests(list(files))

    result = process_file_command_results(_answered(requests, files))

    assert result["/etc/shells"]["parsed"] == ""


def test_a_batch_of_one_answers_like_a_batch_of_many() -> None:
    """Test the single-result shape the result processor collapses to
    is unpacked the same way a list of them is."""
    requests = get_file_command_requests(["/etc/shells"])

    result = process_file_command_results(
        _answered(requests, {"/etc/shells": "/bin/sh\n"})
    )

    assert result["/etc/shells"]["parsed"] == "/bin/sh\n"


def test_other_commands_in_the_batch_are_left_alone() -> None:
    """Test the reads are taken out of a batch that carries probes
    too, which is the whole point of putting them there."""
    requests = get_file_command_requests(["/etc/shells"])
    probe = {
        "type": "uname",
        "implementation": "posix",
        "args": {},
        "command": ("uname", "-a"),
        "rc": 0,
        "stdout": "Darwin host 25.5.0",
    }

    results = process_file_command_results(
        _answered(requests, {"/etc/shells": "/bin/sh\n"}) + [probe]
    )

    assert set(results) == {"/etc/shells"}


def test_no_reads_in_the_batch_is_no_results() -> None:
    """Test a gather that read no files takes nothing out."""
    assert process_file_command_results([]) == {}
