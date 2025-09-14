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

"""Mount-related test utilities."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def find_mount_by_target(mounts_list: List[Dict[str, Any]], target: str) -> Optional[Dict[str, Any]]:
    """Find a mount entry by target in a list of mounts.
    
    :param mounts_list: List of mount dictionaries
    :param target: Target mount point to search for
    :returns: Mount dictionary if found, None otherwise
    """
    for mount in mounts_list:
        if mount.get("target") == target:
            return mount
    return None


def assert_mount_has_fields(
    mount: Dict[str, Any],
    required_fields: List[str],
    optional_fields: Optional[List[str]] = None
) -> None:
    """Assert that a mount has required fields and optionally check for optional fields.
    
    :param mount: Mount dictionary to check
    :param required_fields: List of fields that must be present
    :param optional_fields: List of fields that may or may not be present
    :raises AssertionError: If any required field is missing
    """
    for field in required_fields:
        assert field in mount, f"Mount missing required field: {field}"
    
    if optional_fields:
        # Just document which optional fields are present for debugging
        present_optional = [f for f in optional_fields if f in mount]
        missing_optional = [f for f in optional_fields if f not in mount]
        # This is just for debugging, not an assertion


def convert_dict_mounts_to_list(mounts_dict: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert old dict-style mounts to new list-style mounts.
    
    Helper for updating test expectations from the old format where mounts
    were keyed by mount point to the new format where mounts are a list
    with a 'target' field.
    
    :param mounts_dict: Dictionary keyed by mount point
    :returns: List of mount dictionaries with 'target' field added
    """
    mounts_list = []
    for mount_point, mount_info in mounts_dict.items():
        mount_entry = mount_info.copy()
        mount_entry["target"] = mount_point
        mounts_list.append(mount_entry)
    return mounts_list