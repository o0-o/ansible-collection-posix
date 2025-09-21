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

"""Uname parsing utilities."""

from __future__ import annotations

from typing import Any, Dict, List, Union

from ansible_collections.o0_o.posix.plugins.module_utils.jc_utils import (
    jc_parse,
)

try:
    from ansible_collections.o0_o.utils.plugins.module_utils import (
        parse_hostname,
    )

    HAS_PARSE_HOSTNAME = True
except ImportError:
    HAS_PARSE_HOSTNAME = False


def parse_uname_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a single uname entry from jc output to normalized format.

    Converts jc's uname field names to standardized format:
    - kernel_name → kernel.name and kernel.pretty
    - kernel_release → kernel.version.id
    - machine/processor/hardware_platform → architecture
    - node_name → hostname.short and hostname.long (if FQDN)

    :param entry: Single uname entry from jc parser
    :returns: Normalized entry dict with kernel, architecture, hostname
    :raises ValueError: If hostname parsing fails
    """
    norm_entry = {}

    # Kernel information
    if "kernel_name" in entry:
        kernel = {
            "pretty": entry["kernel_name"],
            "name": entry["kernel_name"].lower().replace(" ", "_"),
        }
        if "kernel_release" in entry:
            kernel["version"] = {"id": entry["kernel_release"]}
        norm_entry["kernel"] = kernel

    # Architecture
    if "machine" in entry:
        norm_entry["architecture"] = entry["machine"]
    elif "processor" in entry and entry["processor"] != "unknown":
        norm_entry["architecture"] = entry["processor"]
    elif (
        "hardware_platform" in entry
        and entry["hardware_platform"] != "unknown"
    ):
        norm_entry["architecture"] = entry["hardware_platform"]

    # Hostname - use short and long (if present)
    if "node_name" in entry:
        if not HAS_PARSE_HOSTNAME:
            # If hostname filter is not available, raise error
            raise ValueError(
                "Hostname parsing requires the o0_o.utils collection. "
                "Please install it with: "
                "ansible-galaxy collection install o0_o.utils"
            )

        try:
            hostname_data = parse_hostname(entry["node_name"])
        except Exception as e:
            raise ValueError(
                f"Failed to parse hostname: {type(e).__name__}: {e}"
            ) from e

        # Always include short
        hostname_facts = {"short": hostname_data.get("short", "")}

        # Include long only if it's present (FQDN)
        if "long" in hostname_data:
            hostname_facts["long"] = hostname_data["long"]

        norm_entry["hostname"] = hostname_facts

    return norm_entry


def uname(config: Union[str, List[str], Dict[str, Any]]) -> Dict[str, Any]:
    """Process uname data - parse command output into structured format.

    Returns data structure with:
    - kernel: dict with name, pretty, and version fields
    - architecture: system architecture string
    - hostname: dict with short and optionally long (FQDN)

    :param config: Uname command output as string, list of lines, or
                   dict
    :returns: Normalized uname data structure
    :raises ValueError: If parsing fails
    :raises ImportError: If jc is not available
    """
    # Handle list input (e.g., stdout_lines from command module)
    if isinstance(config, list):
        config = "\n".join(config)

    # Parse with jc_parse (handles both string and dict inputs)
    parsed = jc_parse("uname", config)

    # uname returns a single dict, not a list
    # Normalize and return directly
    return parse_uname_entry(parsed)
