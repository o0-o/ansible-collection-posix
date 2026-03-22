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

"""Uname parsing utilities.

The canonical parser is ``_parse_uname`` which implements the
COMMAND_SPEC ``(output, e_prefix) -> (parsed, errors)`` contract.
The ``uname()`` function is a convenience wrapper for filter use.
"""

from __future__ import annotations

from typing import Any, Optional

from ansible_collections.o0_o.core.plugins.module_utils import (
    process_all_command_results,
    process_command_spec,
)

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


def _parse_uname_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Parse a single uname entry from jc output to normalized format.

    Converts jc's uname field names to standardized format:
    - kernel_name -> kernel.name and kernel.pretty
    - kernel_release -> kernel.version.id
    - machine/processor/hardware_platform -> architecture
    - node_name -> hostname.short and hostname.long (if FQDN)

    :param dict[str, Any] entry: Single uname entry from jc parser
    :returns dict[str, Any]: Normalized entry dict with kernel,
        architecture, hostname
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


def _parse_uname(
    output: str,
    e_prefix: str,
) -> tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
    """Canonical COMMAND_SPEC parser for uname -a output.

    Parses raw uname -a stdout into a normalized dict with kernel,
    architecture, and hostname fields.  Uses jc for primary parsing
    with a manual fallback for platforms jc cannot handle (e.g.
    OpenBSD).

    :param str output: Raw stdout from ``uname -a``
    :param str e_prefix: Error prefix for context in error messages
    :returns tuple[Optional[dict[str, Any]], Optional[list[Exception]]]:
        Parsed uname data and list of errors (if any)
    """
    errors = []
    text = (output or "").strip()
    if not text:
        errors.append(ValueError(f"{e_prefix}Empty uname output"))
        return None, errors

    # Try jc first
    try:
        parsed = jc_parse("uname", text)
        return _parse_uname_entry(parsed), errors
    except ValueError:
        pass

    # Fallback parsing for platforms where jc fails
    tokens = text.split()

    # OpenBSD format: OpenBSD <node> <release> <build> <arch>
    if tokens[0] == "OpenBSD" and len(tokens) >= 5:
        entry = {
            "kernel_name": tokens[0],
            "node_name": tokens[1],
            "kernel_release": tokens[2],
            "machine": tokens[-1],
        }
        try:
            return _parse_uname_entry(entry), errors
        except Exception as e:
            errors.append(
                ValueError(f"{e_prefix}OpenBSD fallback failed: {e}")
            )
            return None, errors

    errors.append(
        ValueError(f"{e_prefix}Failed to parse uname output: {text}")
    )
    return None, errors


def get_uname_command_requests() -> list[dict[str, Any]]:
    """Build command requests for uname fact gathering.

    :returns list[dict[str, Any]]: Command requests for run plugin
    """
    from ansible_collections.o0_o.posix.plugins.module_utils.command_spec import (  # noqa: E501
        UNAME_COMMAND_SPEC,
    )

    return process_command_spec(UNAME_COMMAND_SPEC)


def process_uname_command_results(
    cmds_completed: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[Exception]]:
    """Process uname command results into structured facts.

    Takes command results from run plugin and returns facts organized
    into the namespace structure used by the facts module.

    :param list[dict[str, Any]] cmds_completed: List of command
        result dicts from run plugin
    :returns tuple[dict[str, Any], list[Exception]]: Tuple of
        (facts_dict, errors) where facts_dict has o0_os, o0_network,
        and o0_hardware namespace keys
    """
    processed = process_all_command_results(cmds_completed)
    errors = []

    uname_result = processed.get("uname")
    if uname_result is None:
        return {}, [ValueError("No uname result found")]

    errors.extend(uname_result.get("errors", []))
    uname_facts = uname_result.get("parsed")

    if not uname_facts:
        return {}, errors

    # Map uname fields to fact namespaces
    facts = {}

    if "kernel" in uname_facts:
        facts.setdefault("o0_os", {})["kernel"] = uname_facts["kernel"]

    if "hostname" in uname_facts:
        facts.setdefault("o0_network", {})["hostname"] = uname_facts[
            "hostname"
        ]

    if "architecture" in uname_facts:
        facts.setdefault("o0_hardware", {}).setdefault("baseboard", {})[
            "architecture"
        ] = uname_facts["architecture"]

    return facts, errors
