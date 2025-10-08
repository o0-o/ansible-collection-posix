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

"""Unit tests for hosts module_utils helpers."""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils import hosts_utils


def test_parse_hosts_entry_with_aliases() -> None:
    """Test parsing entry with hostname and aliases."""

    entry = {
        "ip": "192.168.1.10",
        "hostname": ["server1.example.com", "server1", "srv1"],
    }

    result = hosts_utils.parse_hosts_entry(entry)

    assert result["address"] == "192.168.1.10"
    assert result["hostnames"] == ["server1.example.com", "server1", "srv1"]


def test_parse_hosts_entry_without_aliases() -> None:
    """Test parsing entry with only hostname."""

    entry = {
        "ip": "127.0.0.1",
        "hostname": ["localhost"],
    }

    result = hosts_utils.parse_hosts_entry(entry)

    assert result["address"] == "127.0.0.1"
    assert result["hostnames"] == ["localhost"]


def test_parse_hosts_entry_requires_ip() -> None:
    """Missing IP address raises ValueError."""

    entry = {"hostname": ["localhost"]}

    with pytest.raises(ValueError, match="Missing ip"):
        hosts_utils.parse_hosts_entry(entry)


def test_parse_hosts_entry_empty_entry() -> None:
    """Empty entry raises ValueError."""

    with pytest.raises(ValueError, match="Empty hosts entry"):
        hosts_utils.parse_hosts_entry({})


def test_generate_hosts_entry_with_aliases() -> None:
    """Test generating entry with aliases."""

    entry = {
        "address": "192.168.1.10",
        "hostnames": ["server1.example.com", "server1", "srv1"],
    }

    line = hosts_utils.generate_hosts_entry(entry)

    assert "192.168.1.10" in line
    assert "server1.example.com" in line
    assert "server1" in line
    assert "srv1" in line


def test_generate_hosts_entry_without_aliases() -> None:
    """Test generating entry without aliases."""

    entry = {
        "address": "127.0.0.1",
        "hostnames": ["localhost"],
    }

    line = hosts_utils.generate_hosts_entry(entry)

    assert line == "127.0.0.1\tlocalhost"


def test_generate_hosts_entry_requires_address() -> None:
    """Missing address raises ValueError."""

    entry = {"hostnames": ["localhost"]}

    with pytest.raises(ValueError, match="Missing address"):
        hosts_utils.generate_hosts_entry(entry)


def test_generate_hosts_entry_requires_hostname() -> None:
    """Missing hostnames raises ValueError."""

    entry = {"address": "127.0.0.1"}

    with pytest.raises(ValueError, match="Missing hostnames"):
        hosts_utils.generate_hosts_entry(entry)


def test_hosts_parses_string_input() -> None:
    """Test hosts() function delegates to jc_parse for string input."""

    jc_return: List[Dict[str, Any]] = [
        {
            "ip": "127.0.0.1",
            "hostname": ["localhost"],
        },
        {
            "ip": "::1",
            "hostname": ["localhost", "ip6-localhost"],
        },
    ]

    with patch.object(
        hosts_utils, "jc_parse", return_value=jc_return
    ) as mock_parse:
        result = hosts_utils.hosts("127.0.0.1 localhost\n::1 localhost")

    mock_parse.assert_called_once_with(
        "hosts", "127.0.0.1 localhost\n::1 localhost"
    )
    assert len(result) == 2
    assert result[0]["address"] == "127.0.0.1"
    assert result[0]["hostnames"] == ["localhost"]
    assert result[1]["address"] == "::1"
    assert result[1]["hostnames"] == ["localhost", "ip6-localhost"]


def test_hosts_generates_from_list() -> None:
    """Test hosts() function generates text from list input."""

    data = [
        {
            "address": "127.0.0.1",
            "hostnames": ["localhost"],
        },
        {
            "address": "192.168.1.10",
            "hostnames": ["server1.example.com", "server1"],
        },
    ]

    result = hosts_utils.hosts(data)

    assert isinstance(result, str)
    assert "127.0.0.1" in result
    assert "localhost" in result
    assert "192.168.1.10" in result
    assert "server1.example.com" in result
    assert "server1" in result
    assert result.endswith("\n")


def test_hosts_handles_dict_with_content_key() -> None:
    """Test hosts() handles dict with content key (slurp result)."""

    jc_return: List[Dict[str, Any]] = [
        {
            "ip": "127.0.0.1",
            "hostname": ["localhost"],
        }
    ]

    slurp_result = {"content": "127.0.0.1 localhost"}

    with patch.object(
        hosts_utils, "jc_parse", return_value=jc_return
    ) as mock_parse:
        result = hosts_utils.hosts(slurp_result)

    mock_parse.assert_called_once_with("hosts", "127.0.0.1 localhost")
    assert len(result) == 1


def test_hosts_handles_dict_with_stdout_key() -> None:
    """Test hosts() handles dict with stdout key (command result)."""

    jc_return: List[Dict[str, Any]] = [
        {
            "ip": "127.0.0.1",
            "hostname": ["localhost"],
        }
    ]

    command_result = {"stdout": "127.0.0.1 localhost"}

    with patch.object(
        hosts_utils, "jc_parse", return_value=jc_return
    ) as mock_parse:
        result = hosts_utils.hosts(command_result)

    mock_parse.assert_called_once_with("hosts", "127.0.0.1 localhost")
    assert len(result) == 1


def test_hosts_handles_list_of_lines() -> None:
    """Test hosts() handles list of lines input."""

    jc_return: List[Dict[str, Any]] = [
        {
            "ip": "127.0.0.1",
            "hostname": ["localhost"],
        }
    ]

    lines = ["127.0.0.1 localhost", "::1 localhost"]

    with patch.object(
        hosts_utils, "jc_parse", return_value=jc_return
    ) as mock_parse:
        result = hosts_utils.hosts(lines)

    mock_parse.assert_called_once_with(
        "hosts", "127.0.0.1 localhost\n::1 localhost"
    )


def test_hosts_skips_invalid_entries() -> None:
    """Test that invalid entries are skipped during parsing."""

    jc_return: List[Dict[str, Any]] = [
        {
            "ip": "127.0.0.1",
            "hostname": ["localhost"],
        },
        {},  # Invalid entry
        {
            "hostname": ["missing-ip"],  # Missing IP
        },
    ]

    with patch.object(hosts_utils, "jc_parse", return_value=jc_return):
        result = hosts_utils.hosts("test content")

    # Only the valid entry should be returned
    assert len(result) == 1
    assert result[0]["address"] == "127.0.0.1"
