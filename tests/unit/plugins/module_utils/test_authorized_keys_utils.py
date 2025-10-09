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

"""Unit tests for authorized_keys module_utils helpers."""

from __future__ import annotations

import base64
from typing import Any, Dict, List

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils import (
    authorized_keys,
    parse_authorized_keys,
    parse_authorized_keys_entry,
)


def test_parse_simple_ssh_rsa_key() -> None:
    """Test parsing a simple SSH RSA key."""
    line = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ user@example.com"
    result = parse_authorized_keys_entry(line)

    assert result is not None
    assert result["type"] == "ssh-rsa"
    assert result["key"] == "AAAAB3NzaC1yc2EAAAADAQABAAABAQ"
    assert result["comment"] == "user@example.com"


def test_parse_ssh_ed25519_key() -> None:
    """Test parsing an Ed25519 key."""
    line = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFq deploy-key"
    result = parse_authorized_keys_entry(line)

    assert result is not None
    assert result["type"] == "ssh-ed25519"
    assert result["key"] == "AAAAC3NzaC1lZDI1NTE5AAAAIFq"
    assert result["comment"] == "deploy-key"


def test_parse_key_without_comment() -> None:
    """Test parsing a key without a comment."""
    line = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ"
    result = parse_authorized_keys_entry(line)

    assert result is not None
    assert result["type"] == "ssh-rsa"
    assert result["key"] == "AAAAB3NzaC1yc2EAAAADAQABAAABAQ"
    assert "comment" not in result


def test_parse_key_with_from_option() -> None:
    """Test parsing a key with 'from' restriction."""
    line = 'from="192.168.1.*" ssh-rsa AAAAB3NzaC1yc2E restricted'
    result = parse_authorized_keys_entry(line)

    assert result is not None
    assert result["type"] == "ssh-rsa"
    assert result["key"] == "AAAAB3NzaC1yc2E"
    assert result["comment"] == "restricted"
    assert "options" in result
    assert len(result["options"]) == 1
    assert result["options"][0]["name"] == "from"
    assert result["options"][0]["value"] == "192.168.1.*"


def test_parse_key_with_command_option() -> None:
    """Test parsing a key with 'command' restriction."""
    line = 'command="/usr/bin/backup" ssh-rsa AAAAB3NzaC backup-script'
    result = parse_authorized_keys_entry(line)

    assert result is not None
    assert result["type"] == "ssh-rsa"
    assert "options" in result
    assert result["options"][0]["name"] == "command"
    assert result["options"][0]["value"] == "/usr/bin/backup"


def test_parse_key_with_multiple_options() -> None:
    """Test parsing a key with multiple options."""
    line = (
        'no-port-forwarding,no-X11-forwarding,command="/bin/ls" '
        'ssh-rsa AAAAB3NzaC restricted-key'
    )
    result = parse_authorized_keys_entry(line)

    assert result is not None
    assert result["type"] == "ssh-rsa"
    assert "options" in result
    assert len(result["options"]) == 3
    assert result["options"][0]["name"] == "no-port-forwarding"
    assert result["options"][0]["value"] is None
    assert result["options"][1]["name"] == "no-X11-forwarding"
    assert result["options"][1]["value"] is None
    assert result["options"][2]["name"] == "command"
    assert result["options"][2]["value"] == "/bin/ls"


def test_parse_ecdsa_key() -> None:
    """Test parsing an ECDSA key."""
    line = (
        "ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTY ecdsa-key"
    )
    result = parse_authorized_keys_entry(line)

    assert result is not None
    assert result["type"] == "ecdsa-sha2-nistp256"
    assert result["key"] == "AAAAE2VjZHNhLXNoYTItbmlzdHAyNTY"


def test_parse_comment_line() -> None:
    """Test that comment lines return None."""
    line = "# This is a comment"
    result = parse_authorized_keys_entry(line)

    assert result is None


def test_parse_empty_line() -> None:
    """Test that empty lines return None."""
    result = parse_authorized_keys_entry("")
    assert result is None

    result = parse_authorized_keys_entry("   ")
    assert result is None


def test_parse_invalid_line() -> None:
    """Test that invalid lines return None."""
    line = "not-a-valid-key-type AAAAB3NzaC"
    result = parse_authorized_keys_entry(line)

    assert result is None


def test_parse_authorized_keys_multiple_entries() -> None:
    """Test parsing multiple authorized_keys entries."""
    content = """
# User keys
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ user@example.com
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFq deploy-key

# Restricted keys
from="10.0.0.*" ssh-rsa AAAAB3NzaC1yc2E restricted
"""

    result = parse_authorized_keys(content)

    assert len(result) == 3
    assert result[0]["type"] == "ssh-rsa"
    assert result[0]["comment"] == "user@example.com"
    assert result[1]["type"] == "ssh-ed25519"
    assert result[2]["type"] == "ssh-rsa"
    assert "options" in result[2]


def test_parse_authorized_keys_from_list() -> None:
    """Test parsing from a list of lines."""
    lines = [
        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ user1",
        "# Comment",
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFq user2",
    ]

    result = parse_authorized_keys(lines)

    assert len(result) == 2
    assert result[0]["comment"] == "user1"
    assert result[1]["comment"] == "user2"


def test_authorized_keys_with_raw_string() -> None:
    """Test authorized_keys wrapper with raw string."""
    content = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ user@example.com"
    result = authorized_keys(content)

    assert len(result) == 1
    assert result[0]["type"] == "ssh-rsa"


def test_authorized_keys_with_command_result() -> None:
    """Test authorized_keys wrapper with command result dict."""
    cmd_result = {
        "stdout": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ user@host",
        "rc": 0,
    }
    result = authorized_keys(cmd_result)

    assert len(result) == 1
    assert result[0]["type"] == "ssh-rsa"


def test_authorized_keys_with_slurp_result() -> None:
    """Test authorized_keys wrapper with slurp result dict."""
    content = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFq deploy"
    encoded_content = base64.b64encode(content.encode()).decode()

    slurp_result = {"content": encoded_content, "encoding": "base64"}
    result = authorized_keys(slurp_result)

    assert len(result) == 1
    assert result[0]["type"] == "ssh-ed25519"


def test_authorized_keys_with_pre_parsed_list() -> None:
    """Test authorized_keys wrapper with already parsed data."""
    parsed: List[Dict[str, Any]] = [
        {"type": "ssh-rsa", "key": "AAAAB3...", "comment": "test"}
    ]

    result = authorized_keys(parsed)

    assert result == parsed


def test_authorized_keys_empty_input() -> None:
    """Test authorized_keys with empty input."""
    assert authorized_keys("") == []
    assert authorized_keys([]) == []
    assert authorized_keys({}) == []


def test_parse_key_with_restrict_option() -> None:
    """Test parsing key with 'restrict' option."""
    line = 'restrict,command="/backup" ssh-rsa AAAAB3... backup'
    result = parse_authorized_keys_entry(line)

    assert result is not None
    assert "options" in result
    assert result["options"][0]["name"] == "restrict"
    assert result["options"][1]["name"] == "command"


def test_parse_sk_key_types() -> None:
    """Test parsing security key types."""
    line1 = "sk-ssh-ed25519@openssh.com AAAAC3... security-key"
    result1 = parse_authorized_keys_entry(line1)
    assert result1 is not None
    assert result1["type"] == "sk-ssh-ed25519@openssh.com"

    line2 = "sk-ecdsa-sha2-nistp256@openssh.com AAAAE2... hw-key"
    result2 = parse_authorized_keys_entry(line2)
    assert result2 is not None
    assert result2["type"] == "sk-ecdsa-sha2-nistp256@openssh.com"


def test_parse_key_comment_with_spaces() -> None:
    """Test parsing key with multi-word comment."""
    line = "ssh-rsa AAAAB3... User Name <user@example.com>"
    result = parse_authorized_keys_entry(line)

    assert result is not None
    assert result["comment"] == "User Name <user@example.com>"


def test_authorized_keys_filters_invalid_lines() -> None:
    """Test that invalid lines are skipped during parsing."""
    content = """
ssh-rsa AAAAB3... valid-key
invalid line with no key type
# Comment line
another-invalid-line

ssh-ed25519 AAAAC3... another-valid-key
"""
    result = parse_authorized_keys(content)

    assert len(result) == 2
    assert result[0]["type"] == "ssh-rsa"
    assert result[1]["type"] == "ssh-ed25519"
