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

"""Base classes and utilities for filesystem-related filters."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from ansible_collections.o0_o.posix.plugins.module_utils.storage_drivers import STORAGE_DRIVERS

try:
    from ansible_collections.o0_o.utils.plugins.filter import SiFilter

    HAS_SI_FILTER = True
    _si_filter = SiFilter()
except ImportError:
    HAS_SI_FILTER = False
    _si_filter = None


class StorageBase:
    """Base class for storage classification and facts formatting."""

    def format_storage_as_facts(self, parsed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format parsed storage data for Ansible facts structure.

        Expects normalized storage data with standardized keys:
        - mount: str - The target storage point path
        - source: str - The source device/filesystem (optional)
        - driver: str - The filesystem driver (Note: "driver" is used loosely to
          describe the mechanism by which the storage object relates to the kernel)
        - options: List[str] - Storage options

        Additional optional keys preserved:
        - dump: int - Dump frequency (from fstab)
        - pass: int - fsck pass number (from fstab)

        Important: This method distinguishes between undefined and None values:
        - Undefined (key not present): Value is unknown or ambiguous. The key
          will not appear in the output storage_entry dictionary.
        - None (key present with None value): Value is definitively absent or
          not applicable. The key will appear in storage_entry with value None.

        For example, virtual filesystems like tmpfs have source=None (definitively
        no backing device), while a storage parsed_entry from df output might not include source
        information at all (undefined/unknown).

        :param parsed: Normalized storage data
        :returns: List of storage entries with facts structure
        """
        result = []

        for parsed_entry in parsed:
            # Keys should be set explicity to None if they are
            # definitively irrelevant or absent. Key should be excluded
            # entirely if their value is unknown or ambiguous.
            storage_entry = {}

            if "class" in parsed_entry:
                storage_entry["class"] = parsed_entry["class"]

            # Handle mount
            if "mount" in parsed_entry:

                # Handle swap entries
                if parsed_entry.get("driver", '').lower() == "swap":
                    storage_entry["class"] = "paging"
                else:
                    storage_entry["mount"] = parsed_entry["mount"]
                    # Only filesystems have mount points
                    storage_entry["class"] = "filesystem"

            # Handle driver
            if "driver" in parsed_entry:
                parsed_driver = parsed_entry["driver"].lower()
                storage_entry["driver"] = {}
                if parsed_driver == "fuseblk":
                    storage_entry["driver"]["fuse"] = {
                        "block": True
                    }
                elif (
                    parsed_driver.startswith("fuse.") or
                    parsed_driver.endswith("-fuse") or
                    parsed_driver in STORAGE_DRIVERS and
                    "driver" in STORAGE_DRIVERS[parsed_driver] and
                    "fuse" in STORAGE_DRIVERS[parsed_driver]["driver"]
                ):
                    storage_entry["driver"]["fuse"] = {
                        "type": re.sub(r'(^fuse\.)|(-fuse$)', '', parsed_driver),
                    }
                else:
                    storage_entry["driver"] = parsed_driver
                del parsed_driver

            # Handle source = None
            if (
                "source" in parsed_entry and
                isinstance(parsed_entry["source"], str)
            ):
                parsed_source = parsed_entry["source"]

                # Check if source is actually a driver (like tmpfs, proc, etc.)
                # If so, use it as the driver and clear source
                if (
                    parsed_source.lower() in ("-", "none") or
                    "driver" in parsed_entry
                ):
                    # Source is unambiguously None
                    storage_entry["source"] = None

                elif "driver" not in storage_entry:
                    source_lower = parsed_source.lower()
                    if source_lower in STORAGE_DRIVERS:
                        storage_entry["driver"] = source_lower
                    elif source_lower == "shm":
                        # shm is a source that's always mounted as tmpfs
                        storage_entry["driver"] = "tmpfs"

            # Define options
            if (
                "options" in parsed_entry and
                not isinstance(parsed_entry["options"], str)
            ):
                try:
                    options = list(parsed_entry.get("options", []).copy())
                except Exception:
                    pass
                else:
                    storage_entry["options"] = {}
                    for opt in options:
                        split_opt = opt.split("=", 1)
                        # Check for FUSE subtype in options and use it if
                        # driver is generic
                        if (
                            "fuse" in storage_entry.get("driver", {}) and
                            split_opt[0] == "subtype"
                        ):
                            # Extract subtype and use it as driver
                            storage_entry["driver"]["fuse"]["type"] = (
                                split_opt[1] if len(split_opt) > 1 else None
                            )
                            # Don't add subtype to new_options
                        else:
                            storage_entry["options"][split_opt[0]] = (
                                split_opt[1] if len(split_opt) > 1 else True
                            )
                del options

            # Handle comma-separated driver types (from fstab)
            # Split after all classification is done
            # Skip driver field for swap (paging type) since swap isn't a filesystem
            if (
                "driver" in storage_entry and
                isinstance(storage_entry["driver"], str) and
                "," in storage_entry["driver"]
            ):
                storage_entry["driver"] = storage_entry["driver"].split(",")

            # Handle dump field if present (from fstab)
            if "dump" in parsed_entry:
                dump_value = parsed_entry["dump"]
                dump_dict = {}

                # Check if it's a valid integer
                if isinstance(dump_value, int):
                    if dump_value < 0:
                        dump_dict["invalid"] = dump_value
                    else:
                        dump_dict["enabled"] = dump_value > 0
                        if dump_value > 0:
                            dump_dict["days"] = dump_value
                else:
                    # Not an integer
                    dump_dict["invalid"] = dump_value

                storage_entry["dump"] = dump_dict
                del dump_value
                del dump_dict

            # Handle pass field if present (from fstab)
            if "pass" in parsed_entry:
                pass_value = parsed_entry["pass"]
                fsck_dict = {}

                # Check if it's a valid integer
                if isinstance(pass_value, int):
                    if pass_value < 0:
                        # Invalid but treat as disabled (common practice)
                        fsck_dict["invalid"] = pass_value
                        fsck_dict["enabled"] = False
                    else:
                        fsck_dict["enabled"] = pass_value > 0
                        if pass_value > 0:
                            fsck_dict["pass"] = pass_value
                else:
                    # Not an integer
                    fsck_dict["invalid"] = pass_value

                storage_entry["fsck"] = fsck_dict
                del pass_value
                del fsck_dict

            # Handle capacity fields if present (from df)
            if "total" in parsed_entry or "used" in parsed_entry:
                capacity = self.process_capacity_data(parsed_entry)
                if capacity:
                    storage_entry["capacity"] = capacity
                del capacity

            result.append(storage_entry)

        return result

    def process_capacity_data(self, parsed_entry: Dict[str, Any]) -> Dict[str, Any]:
        """Process capacity data from df output in normalized parsed_entry.

        Expected normalized fields in parsed_entry (from df):
        - block_size: Optional block size multiplier (512, 1024, etc)
        - total: Total capacity in blocks (if block_size) or with units
        - used: Used capacity in blocks (if block_size) or with units

        :param parsed_entry: Normalized parsed_entry that may contain capacity fields
        :returns: Structured capacity information dict with pretty formatting
        """
        if not HAS_SI_FILTER or not _si_filter:
            # Can't format without SI filter
            raise ValueError(
                "o0_o.utils.si could not be imported but is required for "
                "processing capacities"
            )

        capacity = {}

        # Get block size if present
        block_size = 1
        raw_block_size = parsed_entry.get("block_size")
        if raw_block_size:
            block_size = _si_filter.si(raw_block_size, binary=True)["bytes"]

        # Process total and used capacity
        for key in ["total", "used"]:
            raw_capacity = parsed_entry.get(key)
            if raw_capacity is not None:
                # Convert to string with units
                if isinstance(raw_capacity, int):
                    # It's in blocks, multiply by block size
                    capacity_str = f"{int(raw_capacity * block_size)}B"
                else:
                    # Already has units
                    capacity_str = str(raw_capacity)

                # Dict with bytes and pretty fields
                capacity[key] = _si_filter.si(capacity_str, binary=True)

        if None not in [capacity.get("total"), capacity.get("used")]:
            # Calculate percentage and round to 2 decimal places
            percent = capacity["used"]["bytes"] / capacity["total"]["bytes"] * 100
            capacity["used"]["percent"] = round(percent, 2)

        return capacity
