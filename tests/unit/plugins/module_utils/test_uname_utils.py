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

"""Unit tests for uname module_utils helpers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils import uname_utils


@pytest.fixture
def hostname_patch():
    """Patch parse_hostname for the duration of a test."""

    with patch.object(
        uname_utils,
        "parse_hostname",
        return_value={"short": "web", "long": "web.example"},
    ):
        yield


def test_parse_uname_entry_builds_kernel_arch_and_hostname(
    hostname_patch,
) -> None:
    """Happy path normalizes kernel, architecture, and hostname data."""

    entry = {
        "kernel_name": "Linux",
        "kernel_release": "5.15.0",
        "machine": "x86_64",
        "node_name": "web.example",
    }

    result = uname_utils.parse_uname_entry(entry)

    assert result["kernel"]["name"] == "linux"
    assert result["kernel"]["version"]["id"] == "5.15.0"
    assert result["architecture"] == "x86_64"
    assert result["hostname"] == {"short": "web", "long": "web.example"}


def test_parse_uname_entry_architecture_fallbacks(hostname_patch) -> None:
    """Use processor/hardware_platform when machine is missing."""

    entry = {"processor": "amd64"}
    result = uname_utils.parse_uname_entry(entry)
    assert result["architecture"] == "amd64"

    entry = {"processor": "unknown", "hardware_platform": "ppc"}
    result = uname_utils.parse_uname_entry(entry)
    assert result["architecture"] == "ppc"


def test_parse_uname_entry_requires_utils_collection() -> None:
    """Missing utils collection raises ValueError for hostname."""

    entry = {"node_name": "web"}
    with patch.object(uname_utils, "HAS_PARSE_HOSTNAME", False):
        with pytest.raises(ValueError, match="o0_o.utils collection"):
            uname_utils.parse_uname_entry(entry)


def test_uname_uses_jc_parse() -> None:
    """uname helper delegates to jc_parse and normalizes entry."""

    jc_result = {
        "kernel_name": "Linux",
        "node_name": "host",
    }

    with patch.object(
        uname_utils, "jc_parse", return_value=jc_result
    ) as mock_parse:
        with patch.object(
            uname_utils,
            "parse_hostname",
            return_value={"short": "host"},
        ):
            result = uname_utils.uname("uname -a output")

    mock_parse.assert_called_once_with("uname", "uname -a output")
    assert result["hostname"]["short"] == "host"


def test_uname_fallback_openbsd() -> None:
    """Fallback parsing handles OpenBSD uname when jc fails."""

    obsd = "OpenBSD openbsd.home.johnandlaurel.com 7.6 GENERIC.MP#196 arm64"

    with patch.object(
        uname_utils, "jc_parse", side_effect=ValueError("pop from empty list")
    ):
        with patch.object(
            uname_utils, "parse_hostname", return_value={"short": "openbsd"}
        ):
            result = uname_utils.uname(obsd)

    assert result["kernel"]["name"] == "openbsd"
    assert result["kernel"]["version"]["id"] == "7.6"
    assert result["architecture"] == "arm64"
