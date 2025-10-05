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

"""Utilities for checking standards compliance."""

from __future__ import annotations

from typing import Any, Dict, Optional


def is_posix(facts: Any) -> Optional[bool]:
    """Check if a system is POSIX-compliant based on facts.

    Examines the compliance information in an ansible_facts dict, a
    registered result dict with a 'compliance' key, or a compliance dict
    directly.

    :param facts: Facts dictionary (typically ansible_facts), registered
        result from compliance module, or compliance dict directly
    :returns: True if POSIX-compliant, False if not, None if cannot
        determine
    :raises TypeError: If facts is not a dict
    """
    if not isinstance(facts, dict):
        raise TypeError(
            f"is_posix() requires a dict, got {type(facts).__name__}"
        )

    # Try to get compliance dict from facts
    # First check if there's a 'compliance' key (ansible_facts or
    # registered result)
    if "compliance" in facts:
        compliance = facts.get("compliance")
        if not isinstance(compliance, dict):
            return None
    else:
        # If no 'compliance' key, assume the dict itself is the
        # compliance dict
        compliance = facts

    # If compliance dict is empty, we cannot determine
    if not compliance:
        return None

    # Check for POSIX compliance indicators
    # A system is POSIX-compliant if it has:
    # - POSIX.1 (XSH - System Interfaces) OR
    # - POSIX.2 (XCU - Shell and Utilities) OR
    # - SUS (Single UNIX Specification)

    # Check for SUS compliance (includes POSIX)
    if "sus" in compliance:
        sus = compliance["sus"]
        if isinstance(sus, dict) and "version" in sus:
            return True

    # Check for POSIX compliance
    if "posix" in compliance:
        posix = compliance["posix"]
        if isinstance(posix, dict) and "components" in posix:
            components = posix["components"]
            if isinstance(components, dict):
                # Check for XSH (System Interfaces) or XCU (Shell &
                # Utilities)
                if "xsh" in components or "xcu" in components:
                    return True

    # If we have a compliance dict but no POSIX indicators, system is
    # not POSIX
    # If compliance dict exists but is malformed, return None
    if compliance:
        # Check if compliance has any recognized keys
        if any(k in compliance for k in ["posix", "sus"]):
            # Has recognized keys but no valid POSIX indicators
            return False

    # Cannot determine (compliance dict exists but has no recognized
    # keys)
    return None
