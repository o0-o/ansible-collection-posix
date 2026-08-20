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

"""Unit tests for id module_utils helpers."""

from __future__ import annotations

from typing import Any

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils import (
    get_effective_uid_command_requests,
    id_info,
    process_effective_uid_results,
)

SAMPLE_ID: dict[str, Any] = {
    "uid": {"id": 1000, "name": "o0-o"},
    "gid": {"id": 20, "name": "staff"},
    "groups": [
        {"id": 20, "name": "staff"},
        {"id": 101, "name": "access_bpf"},
        {"id": 12, "name": "everyone"},
        {"id": 61, "name": None},
    ],
}


@pytest.mark.parametrize("config", [SAMPLE_ID, [SAMPLE_ID]])
def test_id_info_key_id(config: Any) -> None:
    """Numeric keyed result maps ids to group metadata."""

    result = id_info(config, key="id")

    assert result == {
        "users": {
            "1000": {
                "name": "o0-o",
                "group": 20,
                "groups": [20, 101, 12, 61],
            }
        },
        "groups": {
            "20": {"name": "staff"},
            "101": {"name": "access_bpf"},
            "12": {"name": "everyone"},
            "61": {"name": None},
        },
    }


def test_id_info_key_name() -> None:
    """Name keyed result maps to friendly names when available."""

    result = id_info(SAMPLE_ID, key="name")

    assert result["users"] == {
        "o0-o": {
            "id": 1000,
            "group": "staff",
            "groups": ["staff", "access_bpf", "everyone", "61"],
        }
    }
    assert result["groups"]["staff"] == {"id": 20}
    assert result["groups"]["access_bpf"] == {"id": 101}
    # Group without name falls back to id string
    assert result["groups"]["61"] == {"id": 61}


def test_id_info_invalid_key() -> None:
    """Invalid key values raise ValueError."""

    with pytest.raises(ValueError, match="Unsupported key"):
        id_info(SAMPLE_ID, key="invalid")


def test_id_info_handles_empty() -> None:
    """Empty input returns empty mappings."""

    result = id_info({}, key="id")
    assert result == {"users": {}, "groups": {}}


def test_effective_uid_request_runs_id_u() -> None:
    """The effective uid is gathered with id -u."""

    requests = get_effective_uid_command_requests()

    assert len(requests) == 1
    assert requests[0]["type"] == "effective_uid"
    assert tuple(requests[0]["command"]) == ("id", "-u")


def _completed_uid(rc: int, stdout: str) -> dict[str, Any]:
    """Build a completed effective_uid command result."""

    requests = get_effective_uid_command_requests()
    return {**requests[0], "rc": rc, "stdout": stdout, "stderr": ""}


def test_process_effective_uid_results() -> None:
    """Numeric output parses to an integer uid."""

    assert process_effective_uid_results([_completed_uid(0, "1000\n")]) == 1000
    assert process_effective_uid_results([_completed_uid(0, "0")]) == 0


def test_process_effective_uid_results_no_answer() -> None:
    """A failed or unparsable id -u yields no uid."""

    assert process_effective_uid_results([]) is None
    assert process_effective_uid_results([_completed_uid(1, "")]) is None
    assert process_effective_uid_results([_completed_uid(0, "root")]) is None
