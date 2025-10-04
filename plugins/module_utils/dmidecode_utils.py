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

"""Utilities for parsing dmidecode output."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from ansible_collections.o0_o.posix.plugins.module_utils.jc_utils import (
    jc_parse,
)

try:
    from ansible_collections.o0_o.utils.plugins.module_utils.si_utils import (
        parse_si,
    )

    HAS_SI_UTILS = True
except ImportError:
    HAS_SI_UTILS = False


def _parse_date_to_epoch(date_str: str) -> Optional[int]:
    """Parse date string to epoch timestamp.

    :param date_str: Date string in MM/DD/YYYY format
    :returns: Unix epoch timestamp or None if parsing fails
    """
    try:
        dt = datetime.strptime(date_str, "%m/%d/%Y")
        return int(dt.timestamp())
    except (ValueError, AttributeError):
        return None


def _clean_feature(feature: str) -> str:
    """Clean up feature string by removing common suffixes.

    Removes phrases like "is/are supported", "is/are provided",
    "service/services", etc. while preserving technical details in
    parentheses.

    :param feature: Raw feature string
    :returns: Cleaned feature string
    """
    # Remove common phrases before parens (preserving the parens)
    cleaned = re.sub(
        r"\s+(is|are) (supported|provided)(\s+\()", r"\3", feature
    )
    # Remove common phrases at end of string
    cleaned = re.sub(r"\s+(is|are) (supported|provided)$", "", cleaned)
    # Remove "service" or "services" before parens or at end
    cleaned = re.sub(r"\s+services?(\s+\()", r"\1", cleaned)
    cleaned = re.sub(r"\s+services?$", "", cleaned)
    return cleaned


def _clean_board_feature(feature: str) -> str:
    """Clean up board feature string.

    :param feature: Raw board feature string (e.g., "Board is a hosting
        board")
    :returns: Cleaned feature string (e.g., "hosting board")
    """
    # Remove "Board is a " or "Board is "
    cleaned = re.sub(r"^Board is a\s+", "", feature)
    cleaned = re.sub(r"^Board is\s+", "", cleaned)
    return cleaned


def _is_meaningless_value(value: str) -> bool:
    """Check if value is meaningless/placeholder.

    Checks for common meaningless values like "Default string", "Other",
    "None", "Not Specified", "Unspecified", sequential digits, etc.

    :param value: Value string to check (case-insensitive)
    :returns: True if value is meaningless
    """
    if not value:
        return True

    lower_value = value.lower()

    # Common meaningless strings
    meaningless = {
        "default string",
        "other",
        "none",
        "not specified",
        "unspecified",
        "unknown",
        "not available",
        "n/a",
    }

    if lower_value in meaningless:
        return True

    # Check for sequential digits like "0123456789" or "123456789"
    if re.match(r"^0?123456789$", value):
        return True

    return False


def _is_invalid_version(version: str) -> bool:
    """Check if version string appears to be invalid/placeholder.

    :param version: Version string to check
    :returns: True if version appears invalid
    """
    # Use the general meaningless value check
    return _is_meaningless_value(version)


def _is_all_zeros_uuid(uuid: str) -> bool:
    """Check if UUID is all zeros.

    :param uuid: UUID string to check
    :returns: True if UUID is all zeros
    """
    # Remove hyphens and check if all remaining chars are zeros
    cleaned = uuid.replace("-", "")
    return cleaned == "0" * len(cleaned)


def _parse_presence(value: str) -> Union[bool, str]:
    """Parse presence string to boolean if possible.

    :param value: String value to parse (case-insensitive)
    :returns: True if "Present", False if "Not Present", otherwise
        passthrough string
    """
    lower_value = value.lower()
    if lower_value == "present":
        return True
    elif lower_value == "not present":
        return False
    return value


def _parse_slot_usage(value: str) -> Optional[bool]:
    """Parse slot usage to populated boolean.

    :param value: Usage string (case-insensitive)
    :returns: True if "In Use", False if "Available"/"Unavailable",
        None otherwise
    """
    lower_value = value.lower()
    if lower_value == "in use":
        return True
    elif lower_value in ("available", "unavailable"):
        return False
    return None


def _parse_slot_length(value: str) -> Optional[bool]:
    """Parse slot length to short boolean.

    :param value: Length string (case-insensitive)
    :returns: True if "Short", False if "Long", None otherwise
    """
    lower_value = value.lower()
    if lower_value == "short":
        return True
    elif lower_value == "long":
        return False
    return None


def _parse_yes_no(value: str) -> Optional[bool]:
    """Parse yes/no string to boolean.

    :param value: Yes/No string (case-insensitive)
    :returns: True if "Yes", False if "No", None otherwise
    """
    lower_value = value.lower()
    if lower_value == "yes":
        return True
    elif lower_value == "no":
        return False
    return None


def _normalize_slot_type(slot_type: str) -> str:
    """Normalize slot type to lowercase key with underscores.

    Converts slot type to lowercase, replaces spaces with underscores,
    and removes any elements (words) that contain numbers.

    :param slot_type: Raw slot type string (e.g., "x8 PCI Express 3 x8")
    :returns: Normalized type key (e.g., "pci_express")
    """
    # Split into words, filter out any containing digits, lowercase
    words = [
        word.lower()
        for word in slot_type.split()
        if not any(char.isdigit() for char in word)
    ]
    # Join with underscores
    return "_".join(words)


def _normalize_device_name(device_name: str) -> str:
    """Normalize device name to lowercase key with underscores.

    Converts device name to lowercase and replaces spaces with
    underscores.

    :param device_name: Raw device name (e.g., "ASPEED Video AST2400")
    :returns: Normalized device key (e.g., "aspeed_video_ast2400")
    """
    return device_name.lower().replace(" ", "_")


def _process_bios(bios_entry: Dict[str, Any]) -> Dict[str, Any]:
    """Process BIOS information entry.

    :param bios_entry: Raw BIOS entry from jc parser
    :returns: Structured BIOS information
    """
    values = bios_entry.get("values", {})
    bios = {"make": values.get("vendor")}

    # Version information (just the version ID, no revision)
    if "version" in values:
        bios["version"] = {"id": values["version"]}

    # Date information
    if "release_date" in values:
        date_dict = {"pretty": values["release_date"]}
        epoch = _parse_date_to_epoch(values["release_date"])
        if epoch is not None:
            date_dict["epoch"] = epoch
        bios["date"] = date_dict

    # Features (cleaned)
    if "characteristics" in values:
        bios["features"] = [
            _clean_feature(f) for f in values["characteristics"]
        ]

    return bios


def _process_bios_language(language_entry: Dict[str, Any]) -> Dict[str, Any]:
    """Process BIOS Language Information entry.

    :param language_entry: Raw BIOS Language entry from jc parser
    :returns: Languages dict with each language as key and enabled status
    """
    values = language_entry.get("values", {})
    languages = {}

    # Get currently installed language
    current = values.get("currently_installed_language")
    if current and not _is_meaningless_value(current):
        current_lang = current
    else:
        current_lang = None

    # Build languages dict from installable list
    installable = values.get("installable_languages_data")
    if installable and isinstance(installable, list):
        for lang in installable:
            if not _is_meaningless_value(lang):
                # Mark as enabled if it's the current language
                languages[lang] = {"enabled": lang == current_lang}

    return languages


def _process_system(system_entry: Dict[str, Any]) -> Dict[str, Any]:
    """Process System information entry.

    :param system_entry: Raw System entry from jc parser
    :returns: Structured system information for hardware top level
    """
    values = system_entry.get("values", {})
    system = {}

    if "manufacturer" in values:
        system["make"] = values["manufacturer"]
    if "product_name" in values:
        system["model"] = values["product_name"]

    # Only include version if not invalid pattern
    version = values.get("version")
    if version and not _is_invalid_version(version):
        system["version"] = {"id": version}

    # Only include serial if not meaningless
    serial = values.get("serial_number")
    if serial and not _is_meaningless_value(serial):
        system["serial"] = serial

    # Only include UUID if not all zeros
    uuid = values.get("uuid")
    if uuid and not _is_all_zeros_uuid(uuid):
        system["uuid"] = uuid

    # Only include SKU if not meaningless
    sku = values.get("sku_number")
    if sku and not _is_meaningless_value(sku):
        system["sku"] = sku

    # Only include family if not meaningless
    family = values.get("family")
    if family and not _is_meaningless_value(family):
        system["family"] = family

    return system


def _process_chassis(chassis_entry: Dict[str, Any]) -> Dict[str, Any]:
    """Process Chassis information entry.

    :param chassis_entry: Raw Chassis entry from jc parser
    :returns: Structured chassis information
    """
    values = chassis_entry.get("values", {})
    chassis = {}

    if "manufacturer" in values:
        chassis["make"] = values["manufacturer"]

    # Only include type if not meaningless
    chassis_type = values.get("type")
    if chassis_type and not _is_meaningless_value(chassis_type):
        chassis["type"] = chassis_type

    # Only include version if not invalid pattern
    version = values.get("version")
    if version and not _is_invalid_version(version):
        chassis["version"] = {"id": version}

    # Only include serial if not meaningless
    serial = values.get("serial_number")
    if serial and not _is_meaningless_value(serial):
        chassis["serial"] = serial

    # Only include asset_tag if not meaningless
    asset_tag = values.get("asset_tag")
    if asset_tag and not _is_meaningless_value(asset_tag):
        chassis["asset_tag"] = asset_tag

    # Only include SKU if not meaningless
    sku = values.get("sku_number")
    if sku and not _is_meaningless_value(sku):
        chassis["sku"] = sku

    # Parse lock presence (case-insensitive)
    if "lock" in values:
        chassis["lock"] = _parse_presence(values["lock"])

    # State fields - passthrough
    if "boot-up_state" in values:
        chassis["boot"] = values["boot-up_state"]
    if "power_supply_state" in values:
        chassis["psu"] = values["power_supply_state"]
    if "thermal_state" in values:
        chassis["thermal"] = values["thermal_state"]

    # Only include security if not meaningless
    security = values.get("security_status")
    if security and not _is_meaningless_value(security):
        chassis["security"] = security

    # Only include height if not meaningless
    height = values.get("height")
    if height and not _is_meaningless_value(height):
        chassis["height"] = height

    return chassis


def _process_baseboard(baseboard_entry: Dict[str, Any]) -> Dict[str, Any]:
    """Process Base Board information entry.

    :param baseboard_entry: Raw Base Board entry from jc parser
    :returns: Structured baseboard information
    """
    values = baseboard_entry.get("values", {})
    baseboard = {}

    if "manufacturer" in values:
        baseboard["make"] = values["manufacturer"]
    if "product_name" in values:
        baseboard["model"] = values["product_name"]
    if "version" in values:
        baseboard["version"] = {"id": values["version"]}

    # Only include serial if not meaningless
    serial = values.get("serial_number")
    if serial and not _is_meaningless_value(serial):
        baseboard["serial"] = serial

    # Only include asset_tag if not meaningless
    asset_tag = values.get("asset_tag")
    if asset_tag and not _is_meaningless_value(asset_tag):
        baseboard["asset_tag"] = asset_tag

    # Only include location if not meaningless
    location = values.get("location_in_chassis")
    if location and not _is_meaningless_value(location):
        baseboard["location"] = location

    # Features (cleaned)
    if "features" in values:
        baseboard["features"] = [
            _clean_board_feature(f) for f in values["features"]
        ]

    return baseboard


def _process_slots(
    slot_entries: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Process system slot information entries.

    Groups slots by type, then by descriptive key (preferred) or index
    (fallback).

    :param slot_entries: List of slot entries from jc parser
    :returns: Nested dict with slot types, then descriptive keys/indices
    """
    import re

    slots_by_type = {}
    # Track designations to check uniqueness per type
    designations_by_type = {}

    # First pass: collect all slots and extract designation keys
    slot_data = []
    for entry in slot_entries:
        values = entry.get("values", {})
        slot = {}

        # Bus address
        if "bus_address" in values:
            slot["bus"] = values["bus_address"]

        # Description (designation)
        designation = values.get("designation")
        if designation:
            slot["description"] = designation

        # Type
        slot_type = values.get("type")
        if not slot_type or _is_meaningless_value(slot_type):
            continue

        slot["type"] = slot_type

        # Populated (from current_usage)
        if "current_usage" in values:
            populated = _parse_slot_usage(values["current_usage"])
            if populated is not None:
                slot["populated"] = populated

        # Short (from length)
        if "length" in values:
            short = _parse_slot_length(values["length"])
            if short is not None:
                slot["short"] = short

        # Index (from id) - used as fallback key
        slot_id = values.get("id")
        if not slot_id:
            continue

        # Features (cleaned characteristics)
        if "characteristics" in values:
            slot["features"] = [
                _clean_feature(f) for f in values["characteristics"]
            ]

        normalized_type = _normalize_slot_type(slot_type)

        # Extract descriptive key from designation
        # (e.g., "CPU2 SLOT1" -> "cpu2_slot1")
        descriptive_key = None
        if designation:
            # Match patterns like "CPU2 SLOT1", "CPU1 SLOT2 PCI-E 3.0 X8"
            match = re.match(r"(CPU\d+\s+SLOT\d+)", designation, re.IGNORECASE)
            if match:
                descriptive_key = match.group(1).lower().replace(" ", "_")

        # Track designation keys for uniqueness check
        if normalized_type not in designations_by_type:
            designations_by_type[normalized_type] = {}
        if descriptive_key:
            if descriptive_key not in designations_by_type[normalized_type]:
                designations_by_type[normalized_type][descriptive_key] = 0
            designations_by_type[normalized_type][descriptive_key] += 1

        slot_data.append(
            {
                "slot": slot,
                "type": normalized_type,
                "descriptive_key": descriptive_key,
                "id": slot_id,
            }
        )

    # Second pass: assign keys based on uniqueness
    for item in slot_data:
        slot = item["slot"]
        normalized_type = item["type"]
        descriptive_key = item["descriptive_key"]
        slot_id = item["id"]

        # Use descriptive key if available and unique, otherwise fall back
        # to ID
        if (
            descriptive_key
            and designations_by_type[normalized_type][descriptive_key] == 1
        ):
            slot_key = descriptive_key
        else:
            slot_key = slot_id

        # Group by normalized type, then by key
        if normalized_type not in slots_by_type:
            slots_by_type[normalized_type] = {}
        slots_by_type[normalized_type][slot_key] = slot

    return slots_by_type


def _process_oem_strings(oem_entries: List[Dict[str, Any]]) -> List[str]:
    """Process OEM Strings information entries.

    :param oem_entries: List of OEM string entries from jc parser
    :returns: List of OEM strings (trailing whitespace stripped)
    """
    oem_strings = []

    for entry in oem_entries:
        values = entry.get("values", {})
        # OEM strings are stored as numbered keys: string_1, string_2, etc.
        for key, value in sorted(values.items()):
            if key.startswith("string_") and value:
                # Strip trailing whitespace from OEM strings
                oem_strings.append(value.rstrip())

    return oem_strings


def _process_config_options(config_entries: List[Dict[str, Any]]) -> List[str]:
    """Process System Configuration Options entries.

    :param config_entries: List of config option entries from jc parser
    :returns: List of configuration options (excluding meaningless values)
    """
    options = []

    for entry in config_entries:
        values = entry.get("values", {})
        # Config options stored as numbered keys: option_1, option_2, etc.
        for key, value in sorted(values.items()):
            if key.startswith("option_") and value:
                # Skip meaningless default values
                if not _is_meaningless_value(value):
                    options.append(value.rstrip())

    return options


def _process_boot_status(boot_entries: List[Dict[str, Any]]) -> Optional[str]:
    """Process System Boot Information entry.

    :param boot_entries: List of boot info entries from jc parser
    :returns: Boot status string or None if not found
    """
    if not boot_entries:
        return None

    values = boot_entries[0].get("values", {})
    status = values.get("status")

    # Only return if not meaningless
    if status and not _is_meaningless_value(status):
        return status

    return None


def _process_memory_array(
    array_entries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Process Physical Memory Array information.

    Merges data from multiple arrays into baseboard memory info.

    :param array_entries: List of memory array entries from jc parser
    :returns: Dict with memory array info for baseboard
    """
    if not array_entries:
        return {}

    # Use first array for common info (usually all arrays have same specs)
    values = array_entries[0].get("values", {})
    memory_info = {}

    # Error correction type (simplified to just the type)
    ecc_type = values.get("error_correction_type")
    if ecc_type and not _is_meaningless_value(ecc_type):
        # Simplify "Multi-bit ECC" to just "multi-bit"
        ecc_lower = ecc_type.lower()
        if "multi-bit" in ecc_lower:
            memory_info["ecc"] = "multi-bit"
        elif "single-bit" in ecc_lower:
            memory_info["ecc"] = "single-bit"
        elif "none" not in ecc_lower:
            memory_info["ecc"] = ecc_type

    # Maximum capacity from all arrays combined
    total_capacity = 0
    for entry in array_entries:
        capacity_str = entry.get("values", {}).get("maximum_capacity")
        if capacity_str and HAS_SI_UTILS:
            parsed = parse_si(capacity_str, binary=True)
            if parsed and "bytes" in parsed:
                total_capacity += parsed["bytes"]

    if total_capacity > 0 and HAS_SI_UTILS:
        # Re-parse to get optimized pretty format
        memory_info["capacity"] = {
            "bytes": total_capacity,
            "pretty": parse_si(f"{total_capacity} B", binary=True).get(
                "pretty", f"{total_capacity} B"
            ),
        }

    return memory_info


def _process_memory_devices(
    device_entries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Process Memory Device information.

    Extracts common memory properties and individual slot info grouped by
    form factor, then by index.

    :param device_entries: List of memory device entries from jc parser
    :returns: Dict with type, synchronous, form_factor, and grouped slots
    """
    memory_info = {}

    # Track common properties from populated slots
    memory_types = set()
    type_details = set()
    form_factors = set()
    slots_by_form_factor = {}

    for entry in device_entries:
        values = entry.get("values", {})

        # Check if slot is populated
        size_str = values.get("size", "")
        populated = (
            size_str
            and not _is_meaningless_value(size_str)
            and "no module" not in size_str.lower()
        )

        # Get form factor for grouping
        form_factor = values.get("form_factor")
        if not form_factor or _is_meaningless_value(form_factor):
            continue

        # Collect common properties from populated slots
        if populated:
            mem_type = values.get("type")
            if mem_type and not _is_meaningless_value(mem_type):
                memory_types.add(mem_type)

            type_detail = values.get("type_detail")
            if type_detail and not _is_meaningless_value(type_detail):
                type_details.add(type_detail.lower())

            form_factors.add(form_factor)

        # Build slot entry
        slot = {}

        # Index (from locator) - used as key
        locator = values.get("locator")
        if not locator or _is_meaningless_value(locator):
            continue

        # Description (from bank_locator)
        bank = values.get("bank_locator")
        if bank and not _is_meaningless_value(bank):
            slot["description"] = bank

        # Populated
        slot["populated"] = populated

        # Group by normalized form factor, then by lowercase locator
        normalized_form_factor = _normalize_slot_type(form_factor)
        if normalized_form_factor not in slots_by_form_factor:
            slots_by_form_factor[normalized_form_factor] = {}
        slots_by_form_factor[normalized_form_factor][locator.lower()] = slot

    # Set common properties (use most common value if multiple)
    if memory_types:
        memory_info["type"] = sorted(memory_types)[0]

    if "synchronous" in type_details:
        memory_info["synchronous"] = True

    return memory_info, slots_by_form_factor


def _process_psus(
    psu_entries: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Process System Power Supply information entries.

    Groups PSUs by make + model with locations for each installed unit.

    :param psu_entries: List of PSU entries from jc parser
    :returns: Dict with make_model as keys, PSU specs and locations
    """
    psus = {}

    for entry in psu_entries:
        values = entry.get("values", {})

        # Model (from "model_part_number" or "name")
        model = values.get("model_part_number")
        if not model or _is_meaningless_value(model):
            # Try name as fallback
            model = values.get("name")
            if not model or _is_meaningless_value(model):
                continue

        # Manufacturer
        make = values.get("manufacturer")
        if not make or _is_meaningless_value(make):
            continue

        # Create normalized key from make + model
        model_key = f"{make}_{model}".lower().replace(" ", "_")

        # Initialize PSU entry if first time seeing this model
        if model_key not in psus:
            psu = {}

            # Manufacturer (make)
            psu["make"] = make

            # Model
            psu["model"] = model

            # Capacity (parse with SI utils if available)
            capacity_str = values.get("max_power_capacity")
            if capacity_str and not _is_meaningless_value(capacity_str):
                if HAS_SI_UTILS:
                    parsed = parse_si(capacity_str)
                    if parsed and "watts" in parsed:
                        psu["capacity"] = {
                            "watts": parsed["watts"],
                            "pretty": parsed.get("pretty", capacity_str),
                        }
                else:
                    # Fallback: just store the raw string
                    psu["capacity"] = {"pretty": capacity_str}

            # Type (e.g., "Switching")
            psu_type = values.get("type")
            if psu_type and not _is_meaningless_value(psu_type):
                psu["type"] = psu_type

            # Input Voltage Range Switching (shortened to "range")
            range_str = values.get("input_voltage_range_switching")
            if range_str and not _is_meaningless_value(range_str):
                psu["range"] = range_str

            # Hot replaceable (parse yes/no to boolean)
            hotswap = values.get("hot_replaceable")
            if hotswap:
                hotswap_bool = _parse_yes_no(hotswap)
                if hotswap_bool is not None:
                    psu["hotswap"] = hotswap_bool

            # Initialize locations dict
            psu["locations"] = {}
            psus[model_key] = psu

        # Build location entry
        # Determine key: prefer location, fall back to power_unit_group
        location_key = None
        use_location_as_key = False

        location = values.get("location")
        if location and not _is_meaningless_value(location):
            location_key = location.lower()
            use_location_as_key = True
        else:
            # Fall back to group
            group_val = values.get("power_unit_group")
            if group_val:
                try:
                    location_key = str(int(group_val))
                except (ValueError, TypeError):
                    if not _is_meaningless_value(str(group_val)):
                        location_key = str(group_val)

        if not location_key:
            continue

        location_data = {}

        # Group (only if location is used as key and group exists)
        if use_location_as_key:
            group_val = values.get("power_unit_group")
            if group_val:
                try:
                    location_data["group"] = str(int(group_val))
                except (ValueError, TypeError):
                    if not _is_meaningless_value(str(group_val)):
                        location_data["group"] = str(group_val)

        # Serial Number
        serial = values.get("serial_number")
        if serial and not _is_meaningless_value(serial):
            location_data["serial"] = serial

        # Revision (can differ per unit)
        revision = values.get("revision")
        if revision and not _is_meaningless_value(revision):
            location_data["revision"] = revision

        # Status
        status = values.get("status")
        if status and not _is_meaningless_value(status):
            location_data["status"] = status

        # Plugged (parse yes/no to boolean for "powered")
        plugged = values.get("plugged")
        if plugged:
            powered_bool = _parse_yes_no(plugged)
            if powered_bool is not None:
                location_data["powered"] = powered_bool

        # Asset tag
        tag = values.get("asset_tag")
        if tag and not _is_meaningless_value(tag):
            location_data["tag"] = tag

        # Add location to PSU
        psus[model_key]["locations"][location_key] = location_data

    return psus


def _process_memory_modules(
    device_entries: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Process Memory Device entries into module-centric structure.

    Groups memory by part number with locations for each installed module.

    :param device_entries: List of memory device entries from jc parser
    :returns: Dict with part numbers as keys, module info and locations
    """
    modules = {}

    for entry in device_entries:
        values = entry.get("values", {})

        # Check if slot is populated
        size_str = values.get("size", "")
        populated = (
            size_str
            and not _is_meaningless_value(size_str)
            and "no module" not in size_str.lower()
        )

        if not populated:
            continue

        # Part Number - used as primary key (normalized to lowercase)
        part_number = values.get("part_number")
        if not part_number or _is_meaningless_value(part_number):
            continue

        part_number_key = part_number.strip().lower()

        # Initialize module entry if first time seeing this part number
        if part_number_key not in modules:
            module = {}

            # Manufacturer (make)
            manufacturer = values.get("manufacturer")
            if manufacturer and not _is_meaningless_value(manufacturer):
                module["make"] = manufacturer

            # Model (same as part number, but original case)
            module["model"] = part_number.strip()

            # Bits (data and total width)
            bits = {}
            data_width = values.get("data_width")
            if data_width and not _is_meaningless_value(data_width):
                try:
                    bits["data"] = int(data_width.split()[0])
                except (ValueError, IndexError):
                    pass

            total_width = values.get("total_width")
            if total_width and not _is_meaningless_value(total_width):
                try:
                    bits["total"] = int(total_width.split()[0])
                except (ValueError, IndexError):
                    pass

            if bits:
                module["bits"] = bits

            # ECC detection based on total width
            # If total width is multiple of 8 but not multiple of 32, assume ECC
            if "total" in bits:
                total = bits["total"]
                if total % 8 == 0 and total % 32 != 0:
                    module["ecc"] = True
                elif total % 32 == 0:
                    module["ecc"] = False

            # Capacity
            if size_str and HAS_SI_UTILS:
                parsed = parse_si(size_str, binary=True)
                if parsed and "bytes" in parsed:
                    module["capacity"] = {
                        "bytes": parsed["bytes"],
                        "pretty": parsed.get("pretty", size_str),
                    }

            # Speed (rated, as speed.max in module spec)
            speed_str = values.get("speed")
            if speed_str and not _is_meaningless_value(speed_str):
                speed_dict = {}
                if HAS_SI_UTILS:
                    parsed = parse_si(speed_str)
                    if parsed:
                        # Try various possible keys from SI parser
                        if "transfers_per_second" in parsed:
                            speed_dict["t/s"] = parsed["transfers_per_second"]
                        elif "megatransfers_per_second" in parsed:
                            speed_dict["t/s"] = (
                                parsed["megatransfers_per_second"] * 1000000
                            )
                        elif "gigatransfers_per_second" in parsed:
                            speed_dict["t/s"] = int(
                                parsed["gigatransfers_per_second"] * 1000000000
                            )
                        speed_dict["pretty"] = parsed.get("pretty", speed_str)
                # If SI didn't provide t/s, parse manually
                if "pretty" in speed_dict and "t/s" not in speed_dict:
                    if "MT/s" in speed_str:
                        try:
                            value = float(speed_str.split()[0])
                            speed_dict["t/s"] = int(value * 1000000)
                        except (ValueError, IndexError):
                            pass
                if speed_dict:
                    module["speed"] = {"max": speed_dict}

            # Voltage (minimum and maximum)
            voltage = {}
            min_voltage = values.get("minimum_voltage")
            if min_voltage and not _is_meaningless_value(min_voltage):
                if HAS_SI_UTILS:
                    parsed = parse_si(min_voltage)
                    if parsed and "volts" in parsed:
                        voltage["minimum"] = {
                            "volts": parsed["volts"],
                            "pretty": parsed.get("pretty", min_voltage),
                        }

            max_voltage = values.get("maximum_voltage")
            if max_voltage and not _is_meaningless_value(max_voltage):
                if HAS_SI_UTILS:
                    parsed = parse_si(max_voltage)
                    if parsed and "volts" in parsed:
                        voltage["maximum"] = {
                            "volts": parsed["volts"],
                            "pretty": parsed.get("pretty", max_voltage),
                        }

            if voltage:
                module["voltage"] = voltage

            # Rank
            rank_str = values.get("rank")
            if rank_str and not _is_meaningless_value(rank_str):
                try:
                    module["rank"] = int(rank_str)
                except (ValueError, TypeError):
                    pass

            # Initialize locations dict
            module["locations"] = {}
            modules[part_number_key] = module

        # Build location entry
        locator = values.get("locator")
        if not locator or _is_meaningless_value(locator):
            continue

        locator_key = locator.lower()
        location = {}

        # Serial Number
        serial = values.get("serial_number")
        if serial and not _is_meaningless_value(serial):
            location["serial"] = serial

        # Configured Speed (can differ from rated speed)
        configured_speed = values.get("configured_memory_speed")
        if configured_speed and not _is_meaningless_value(configured_speed):
            speed_dict = {}
            if HAS_SI_UTILS:
                parsed = parse_si(configured_speed)
                if parsed:
                    # Try various possible keys from SI parser
                    if "transfers_per_second" in parsed:
                        speed_dict["t/s"] = parsed["transfers_per_second"]
                    elif "megatransfers_per_second" in parsed:
                        speed_dict["t/s"] = (
                            parsed["megatransfers_per_second"] * 1000000
                        )
                    elif "gigatransfers_per_second" in parsed:
                        speed_dict["t/s"] = int(
                            parsed["gigatransfers_per_second"] * 1000000000
                        )
                    speed_dict["pretty"] = parsed.get(
                        "pretty", configured_speed
                    )
            # If SI didn't provide t/s, parse manually
            if "pretty" in speed_dict and "t/s" not in speed_dict:
                if "MT/s" in configured_speed:
                    try:
                        value = float(configured_speed.split()[0])
                        speed_dict["t/s"] = int(value * 1000000)
                    except (ValueError, IndexError):
                        pass
            if speed_dict:
                location["speed"] = speed_dict

        # Configured Voltage
        configured_voltage = values.get("configured_voltage")
        if configured_voltage and not _is_meaningless_value(
            configured_voltage
        ):
            if HAS_SI_UTILS:
                parsed = parse_si(configured_voltage)
                if parsed and "volts" in parsed:
                    location["voltage"] = {
                        "volts": parsed["volts"],
                        "pretty": parsed.get("pretty", configured_voltage),
                    }

        # Asset Tag
        asset_tag = values.get("asset_tag")
        if asset_tag and not _is_meaningless_value(asset_tag):
            location["tag"] = asset_tag

        # Set
        mem_set = values.get("set")
        if mem_set and not _is_meaningless_value(mem_set):
            location["set"] = mem_set

        # Add location to module
        modules[part_number_key]["locations"][locator_key] = location

    return modules


def _process_interfaces(port_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Process port connector information entries.

    :param port_entries: List of port connector entries from jc parser
    :returns: Nested dict structure keyed by designators
    """
    interfaces = {}

    for entry in port_entries:
        values = entry.get("values", {})
        internal_ref = values.get("internal_reference_designator", "")
        external_ref = values.get("external_reference_designator", "")
        internal_type = values.get("internal_connector_type")
        external_type = values.get("external_connector_type")
        port_type = values.get("port_type")

        # Skip if no meaningful designators
        if not internal_ref and not external_ref:
            continue

        # Build the port info dict (exclude meaningless values)
        port_info = {}
        if internal_type and not _is_meaningless_value(internal_type):
            port_info["internal"] = internal_type
        if external_type and not _is_meaningless_value(external_type):
            port_info["external"] = external_type
        if port_type and not _is_meaningless_value(port_type):
            port_info["type"] = port_type

        # Determine key structure (all keys lowercase)
        if _is_meaningless_value(external_ref) and " - " in internal_ref:
            # Split on ' - ' and use as nested key
            parts = internal_ref.split(" - ", 1)
            designator = parts[0].strip().lower()
            subkey = parts[1].strip().lower()
            if designator not in interfaces:
                interfaces[designator] = {}
            # Only add if there's meaningful info
            if port_info:
                interfaces[designator][subkey] = port_info
        elif _is_meaningless_value(external_ref):
            # Flatten completely - only add if there's meaningful info
            if port_info:
                interfaces[internal_ref.lower()] = port_info
        else:
            # Normal nested structure
            internal_key = internal_ref.lower()
            if internal_key not in interfaces:
                interfaces[internal_key] = {}
            # Only add if there's meaningful info
            if port_info:
                interfaces[internal_key][external_ref.lower()] = port_info

    return interfaces


def _process_ipmi(ipmi_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Process IPMI Device Information entry.

    :param ipmi_entries: List of IPMI device entries from jc parser
    :returns: IPMI information dict with version
    """
    if not ipmi_entries:
        return {}

    values = ipmi_entries[0].get("values", {})
    ipmi = {}

    # Specification Version
    spec_version = values.get("specification_version")
    if spec_version and not _is_meaningless_value(spec_version):
        ipmi["version"] = {"id": spec_version}

    return ipmi


def _process_onboard_devices(
    device_entries: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Process Onboard Device Information entries.

    :param device_entries: List of onboard device entries from jc parser
    :returns: Dict of devices keyed by normalized device name
    """
    devices = {}

    for entry in device_entries:
        values = entry.get("values", {})

        # Reference Designation - used as key
        designation = values.get("reference_designation")
        if not designation or _is_meaningless_value(designation):
            continue

        device = {}

        # Type (lowercase)
        device_type = values.get("type")
        if device_type and not _is_meaningless_value(device_type):
            device["type"] = device_type.lower()

        # Status (convert to boolean)
        status = values.get("status")
        if status:
            status_lower = status.lower()
            if status_lower == "enabled":
                device["enabled"] = True
            elif status_lower == "disabled":
                device["enabled"] = False

        # Bus Address
        bus_address = values.get("bus_address")
        if bus_address and not _is_meaningless_value(bus_address):
            device["bus"] = bus_address

        # Use normalized designation as key
        device_key = _normalize_device_name(designation)
        devices[device_key] = device

    return devices


def _process_cache(
    cache_entries: List[Dict[str, Any]],
) -> Dict[int, Dict[str, Dict[str, Any]]]:
    """Process Cache Information entries indexed by handle.

    Returns cache info indexed by DMI handle for later association with
    processors. This handles edge cases where different processor models
    may be installed in the same system.

    :param cache_entries: List of cache entries from jc parser
    :returns: Dict of cache info keyed by DMI handle
    """
    import re

    cache_by_handle = {}

    for entry in cache_entries:
        handle = entry.get("handle")
        if not handle:
            continue
        values = entry.get("values", {})

        # Determine cache level from configuration
        configuration = values.get("configuration", "")
        level = None
        if "Level 1" in configuration:
            level = "l1"
        elif "Level 2" in configuration:
            level = "l2"
        elif "Level 3" in configuration:
            level = "l3"

        if not level:
            continue

        # Determine if internal or external
        location = values.get("location", "")
        is_internal = "Internal" in location

        cache_info = {}

        # Installed Size (capacity)
        installed_size = values.get("installed_size")
        if installed_size and not _is_meaningless_value(installed_size):
            if HAS_SI_UTILS:
                parsed = parse_si(installed_size)
                if parsed and "bytes" in parsed:
                    cache_info["capacity"] = {
                        "bytes": parsed["bytes"],
                        "pretty": parsed.get("pretty", installed_size),
                    }

        # System Type (exclude "Other")
        system_type = values.get("system_type")
        if system_type and not _is_meaningless_value(system_type):
            if system_type != "Other":
                cache_info["type"] = system_type

        # Operational Mode
        mode = values.get("operational_mode")
        if mode and not _is_meaningless_value(mode):
            cache_info["mode"] = mode

        # Error Correction Type (ecc or parity booleans)
        ecc_type = values.get("error_correction_type")
        if ecc_type and not _is_meaningless_value(ecc_type):
            if "ECC" in ecc_type:
                cache_info["ecc"] = True
            elif "Parity" in ecc_type:
                cache_info["parity"] = True

        # Associativity (extract integer)
        associativity = values.get("associativity")
        if associativity and not _is_meaningless_value(associativity):
            # Extract number from "8-way Set-associative"
            match = re.search(r"(\d+)-way", associativity)
            if match:
                cache_info["associativity"] = int(match.group(1))

        # Enabled (from Configuration)
        if "Enabled" in configuration:
            cache_info["enabled"] = True
        elif "Disabled" in configuration:
            cache_info["enabled"] = False

        # Determine if internal or external for later sorting
        location = values.get("location", "")
        is_internal = "Internal" in location

        # Store cache info indexed by handle
        if cache_info:
            if handle not in cache_by_handle:
                cache_by_handle[handle] = {
                    "internal": is_internal,
                    "caches": {},
                }
            cache_by_handle[handle]["caches"][level] = cache_info

    return cache_by_handle


def _process_processors(
    processor_entries: List[Dict[str, Any]],
    cache_by_handle: Dict[int, Dict[str, Any]],
) -> tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """Process Processor Information entries with associated caches.

    Groups processors by model with locations for each installed CPU.
    Also returns socket information for baseboard. Caches are associated
    via DMI handle ordering (caches appear before their processor).

    :param processor_entries: List of processor entries from jc parser
    :param cache_by_handle: Dict of cache info keyed by DMI handle
    :returns: Tuple of (processors dict, sockets dict)
    """
    import re

    processors = {}
    sockets = {}
    socket_type = None

    for entry in processor_entries:
        handle = entry.get("handle")
        values = entry.get("values", {})

        # Find caches associated with this processor (by handle proximity)
        # Caches appear before their processor in DMI, with handles like
        # 0x0050-0x0052 (caches) followed by 0x0053 (processor)
        proc_caches = {}
        proc_external_caches = {}
        if handle and cache_by_handle:
            # Convert handle to int for comparison
            try:
                proc_handle_int = int(handle, 16)
            except (ValueError, TypeError):
                proc_handle_int = None

            if proc_handle_int:
                # Look for caches with handles just before this processor
                for cache_handle in cache_by_handle:
                    try:
                        cache_handle_int = int(cache_handle, 16)
                        if cache_handle_int < proc_handle_int:
                            # Check if this cache is close enough (within ~5 handles)
                            if proc_handle_int - cache_handle_int <= 5:
                                cache_data = cache_by_handle[cache_handle]
                                if cache_data.get("internal"):
                                    proc_caches.update(
                                        cache_data.get("caches", {})
                                    )
                                else:
                                    proc_external_caches.update(
                                        cache_data.get("caches", {})
                                    )
                    except (ValueError, TypeError):
                        continue

        # Socket designation - used as location key
        socket_designation = values.get("socket_designation")
        if not socket_designation or _is_meaningless_value(socket_designation):
            continue

        socket_key = socket_designation.lower()

        # Track socket type and population
        if socket_key not in sockets:
            # Get socket type from upgrade field (e.g., "Socket LGA2011-3")
            if not socket_type:
                upgrade = values.get("upgrade")
                if upgrade and not _is_meaningless_value(upgrade):
                    # Extract type (e.g., "LGA2011-3" from "Socket
                    # LGA2011-3")
                    match = re.search(r"(LGA[\w-]+)", upgrade, re.IGNORECASE)
                    if match:
                        socket_type = match.group(1)

            sockets[socket_key] = {"populated": True}

        # Version contains the full model string
        version = values.get("version")
        if not version or _is_meaningless_value(version):
            continue

        # Manufacturer
        make = values.get("manufacturer")
        if not make or _is_meaningless_value(make):
            continue

        # Family
        family = values.get("family")
        if not family or _is_meaningless_value(family):
            family = None

        # Create normalized key from version
        # E.g., "Intel(R) Xeon(R) CPU E5-2620 v3 @ 2.40GHz" ->
        # "intel_xeon_cpu_e5_2620_v3"
        model_key = None
        # Try to extract model without speed
        match = re.search(
            r"(.+?)\s*@\s*[\d.]+\s*[GM]Hz", version, re.IGNORECASE
        )
        if match:
            model_name = match.group(1).strip()
        else:
            model_name = version

        # Remove trademark symbols like (R), (TM), etc.
        model_name = re.sub(r"\([RTM]+\)", "", model_name)

        # Normalize: lowercase, replace spaces/special chars with underscores
        model_key = re.sub(r"[^\w]+", "_", model_name.lower()).strip("_")
        if make:
            # Prepend manufacturer if not already in model
            if make.lower() not in model_key:
                model_key = f"{make.lower()}_{model_key}"

        # Initialize processor entry if first time seeing this model
        if model_key not in processors:
            processor = {}

            # Manufacturer (make)
            processor["make"] = make

            # Family
            if family:
                processor["family"] = family

            # Model (cleaned version string)
            # Remove trademark symbols, @ speed suffix, make, family, CPU/Processor
            cleaned_model = version
            # Remove (R), (TM), etc.
            cleaned_model = re.sub(r"\([RTM]+\)", "", cleaned_model)
            # Remove @ speed suffix
            cleaned_model = re.sub(
                r"\s*@\s*[\d.]+\s*[GM]Hz",
                "",
                cleaned_model,
                flags=re.IGNORECASE,
            )
            # Remove make if present
            if make:
                cleaned_model = re.sub(
                    rf"\b{re.escape(make)}\b",
                    "",
                    cleaned_model,
                    flags=re.IGNORECASE,
                )
            # Remove family if present
            if family:
                cleaned_model = re.sub(
                    rf"\b{re.escape(family)}\b",
                    "",
                    cleaned_model,
                    flags=re.IGNORECASE,
                )
            # Remove CPU/Processor
            cleaned_model = re.sub(
                r"\b(CPU|Processor)\b", "", cleaned_model, flags=re.IGNORECASE
            )
            # Clean up extra whitespace
            cleaned_model = re.sub(r"\s+", " ", cleaned_model).strip()
            processor["model"] = cleaned_model

            # Signature moved to individual locations (per-socket)

            # Cores (total)
            core_count = values.get("core_count")
            if core_count and not _is_meaningless_value(str(core_count)):
                try:
                    processor["cores"] = {"total": int(core_count)}
                except (ValueError, TypeError):
                    pass

            # Threads - EXCLUDED: DMI thread count is unreliable and
            # ambiguous (may be total spec or currently enabled threads,
            # varies by implementation)

            # Speed (max)
            max_speed = values.get("max_speed")
            if max_speed and not _is_meaningless_value(max_speed):
                speed_dict = {}
                if HAS_SI_UTILS:
                    parsed = parse_si(max_speed)
                    if parsed and "hertz" in parsed:
                        speed_dict["hz"] = parsed["hertz"]
                        speed_dict["pretty"] = parsed.get("pretty", max_speed)
                if not speed_dict and "MHz" in max_speed:
                    # Fallback: parse manually
                    try:
                        value = float(max_speed.split()[0])
                        speed_dict = {
                            "hz": int(value * 1000000),
                            "pretty": max_speed,
                        }
                    except (ValueError, IndexError):
                        pass
                if speed_dict:
                    processor["speed"] = {"max": speed_dict}

            # Voltage
            voltage_str = values.get("voltage")
            if voltage_str and not _is_meaningless_value(voltage_str):
                if HAS_SI_UTILS:
                    parsed = parse_si(voltage_str)
                    if parsed and "volts" in parsed:
                        processor["voltage"] = {
                            "volts": parsed["volts"],
                            "pretty": parsed.get("pretty", voltage_str),
                        }

            # External Clock (flattened to just clock)
            ext_clock = values.get("external_clock")
            if ext_clock and not _is_meaningless_value(ext_clock):
                clock_dict = {}
                if HAS_SI_UTILS:
                    parsed = parse_si(ext_clock)
                    if parsed and "hertz" in parsed:
                        clock_dict["hz"] = parsed["hertz"]
                        clock_dict["pretty"] = parsed.get("pretty", ext_clock)
                if not clock_dict and "MHz" in ext_clock:
                    # Fallback: parse manually
                    try:
                        value = float(ext_clock.split()[0])
                        clock_dict = {
                            "hz": int(value * 1000000),
                            "pretty": ext_clock,
                        }
                    except (ValueError, IndexError):
                        pass
                if clock_dict:
                    processor["clock"] = clock_dict

            # Features (flags as abbreviation: description dict)
            flags = values.get("flags")
            if flags and isinstance(flags, list):
                features = {}
                for flag in flags:
                    # Parse "FPU (Floating-point unit on-chip)"
                    match = re.match(r"^([A-Z0-9\-]+)\s*\((.+)\)$", flag)
                    if match:
                        abbr = match.group(1)
                        desc = match.group(2)
                        features[abbr] = desc
                    else:
                        # No parentheses, use as-is
                        features[flag] = flag
                if features:
                    processor["features"] = features

            # Characteristics
            characteristics = values.get("characteristics")
            if characteristics and isinstance(characteristics, list):
                # Clean characteristics similar to features
                cleaned = []
                for char in characteristics:
                    # Remove trailing whitespace and common suffixes
                    cleaned_char = char.strip()
                    if cleaned_char:
                        cleaned.append(cleaned_char)
                if cleaned:
                    processor["characteristics"] = cleaned

            # Initialize locations dict
            processor["locations"] = {}
            processors[model_key] = processor

        # Build location entry
        location = {}

        # Signature (type, family, model, stepping) - per-socket
        signature = values.get("signature")
        if signature:
            sig_dict = {}
            # Parse signature string like "Type 0, Family 6, Model 63,
            # Stepping 2"
            type_match = re.search(r"Type\s+(\d+)", signature)
            if type_match:
                sig_dict["type"] = int(type_match.group(1))
            fam_match = re.search(r"Family\s+(\d+)", signature)
            if fam_match:
                sig_dict["family"] = int(fam_match.group(1))
            mod_match = re.search(r"Model\s+(\d+)", signature)
            if mod_match:
                sig_dict["model"] = int(mod_match.group(1))
            step_match = re.search(r"Stepping\s+(\d+)", signature)
            if step_match:
                sig_dict["stepping"] = int(step_match.group(1))
            if sig_dict:
                location["signature"] = sig_dict

        # Cores enabled (can differ from total)
        core_enabled = values.get("core_enabled")
        if core_enabled and not _is_meaningless_value(str(core_enabled)):
            try:
                location["cores"] = {"enabled": int(core_enabled)}
            except (ValueError, TypeError):
                pass

        # Current speed (per-socket, flattened)
        current_speed = values.get("current_speed")
        if current_speed and not _is_meaningless_value(current_speed):
            speed_dict = {}
            if HAS_SI_UTILS:
                parsed = parse_si(current_speed)
                if parsed and "hertz" in parsed:
                    speed_dict["hz"] = parsed["hertz"]
                    speed_dict["pretty"] = parsed.get("pretty", current_speed)
            if not speed_dict and "MHz" in current_speed:
                # Fallback: parse manually
                try:
                    value = float(current_speed.split()[0])
                    speed_dict = {
                        "hz": int(value * 1000000),
                        "pretty": current_speed,
                    }
                except (ValueError, IndexError):
                    pass
            if speed_dict:
                location["speed"] = speed_dict

        # Serial Number
        serial = values.get("serial_number")
        if serial and not _is_meaningless_value(serial):
            location["serial"] = serial

        # Asset Tag
        tag = values.get("asset_tag")
        if tag and not _is_meaningless_value(tag):
            location["tag"] = tag

        # Part Number
        part = values.get("part_number")
        if part and not _is_meaningless_value(part):
            location["part"] = part

        # Add internal caches to location
        if proc_caches:
            location["cache"] = proc_caches

        # Add location to processor
        processors[model_key]["locations"][socket_key] = location

        # Add external caches to socket in sockets dict
        if proc_external_caches and socket_key in sockets:
            sockets[socket_key]["cache"] = proc_external_caches

    # Add socket type to sockets dict if found
    if socket_type and sockets:
        sockets["type"] = socket_type

    return processors, sockets


def dmidecode(data: Union[str, List[str], Dict[str, Any]]) -> Dict[str, Any]:
    """Parse dmidecode command output into structured hardware dict.

    Uses jc parser to convert dmidecode output into a hierarchical
    hardware structure reflecting physical reality.

    :param data: dmidecode command output - string, list of lines, or
        command result dict
    :returns: Structured hardware information dict
    :raises ValueError: If jc is not available or parsing fails
    """
    # Parse using jc dmidecode parser (handles dict/string/list inputs)
    parsed = jc_parse("dmidecode", data, quiet=True, raw=False)

    # Group entries by type
    entries_by_type = {}
    for entry in parsed:
        entry_type = entry.get("type")
        if entry_type not in entries_by_type:
            entries_by_type[entry_type] = []
        entries_by_type[entry_type].append(entry)

    # Build structured output
    hardware = {}

    # Process System Information (Type 1) - goes at hardware level
    if 1 in entries_by_type:
        hardware.update(_process_system(entries_by_type[1][0]))

    # Process Chassis Information (Type 3)
    if 3 in entries_by_type:
        chassis = _process_chassis(entries_by_type[3][0])
        if chassis:
            hardware["chassis"] = chassis

    # Baseboard section
    baseboard = {}

    # Process Base Board Information (Type 2)
    if 2 in entries_by_type:
        baseboard.update(_process_baseboard(entries_by_type[2][0]))

    # Process BIOS Information (Type 0)
    if 0 in entries_by_type:
        baseboard["bios"] = _process_bios(entries_by_type[0][0])

    # Process BIOS Language Information (Type 13)
    if 13 in entries_by_type and "bios" in baseboard:
        languages = _process_bios_language(entries_by_type[13][0])
        if languages:
            baseboard["bios"]["languages"] = languages

    # Process Port Connector Information (Type 8)
    if 8 in entries_by_type:
        interfaces = _process_interfaces(entries_by_type[8])
        if interfaces:
            baseboard["interfaces"] = interfaces

    # Process IPMI Device Information (Type 38)
    if 38 in entries_by_type:
        ipmi = _process_ipmi(entries_by_type[38])
        if ipmi:
            baseboard["ipmi"] = ipmi

    # Process Onboard Device Information (Type 41)
    if 41 in entries_by_type:
        devices = _process_onboard_devices(entries_by_type[41])
        if devices:
            baseboard["devices"] = devices

    # Process Cache Information (Type 7) - indexed by handle
    cache_by_handle = {}
    if 7 in entries_by_type:
        cache_by_handle = _process_cache(entries_by_type[7])

    # Process Processor Information (Type 4) - with cache association
    processors_data = {}
    if 4 in entries_by_type:
        processors_data, sockets_data = _process_processors(
            entries_by_type[4], cache_by_handle
        )
        if sockets_data:
            baseboard["sockets"] = sockets_data

    # Process memory information under "memory" key
    memory = {}

    # Process Physical Memory Array (Type 16)
    if 16 in entries_by_type:
        memory_array_info = _process_memory_array(entries_by_type[16])
        memory.update(memory_array_info)

    # Collect all slots (both expansion and memory)
    all_slots = {}

    # Process Memory Devices (Type 17) - get properties and slots
    if 17 in entries_by_type:
        memory_device_info, memory_slots = _process_memory_devices(
            entries_by_type[17]
        )
        memory.update(memory_device_info)
        all_slots.update(memory_slots)

    if memory:
        baseboard["memory"] = memory

    # Process System Slot Information (Type 9)
    if 9 in entries_by_type:
        expansion_slots = _process_slots(entries_by_type[9])
        all_slots.update(expansion_slots)

    if all_slots:
        baseboard["slots"] = all_slots

    if baseboard:
        hardware["baseboard"] = baseboard

    # Process OEM Strings (Type 11) - at hardware level
    if 11 in entries_by_type:
        oem_strings = _process_oem_strings(entries_by_type[11])
        if oem_strings:
            hardware["oem"] = oem_strings

    # Process System Configuration Options (Type 12) - at hardware level
    if 12 in entries_by_type:
        config_options = _process_config_options(entries_by_type[12])
        if config_options:
            hardware["config"] = config_options

    # Process System Boot Information (Type 32) - at hardware level
    if 32 in entries_by_type:
        boot_status = _process_boot_status(entries_by_type[32])
        if boot_status:
            hardware["status"] = boot_status

    # Process System Power Supply (Type 39) - at hardware level
    if 39 in entries_by_type:
        power = _process_psus(entries_by_type[39])
        if power:
            hardware["power"] = power

    # Process Memory Devices (Type 17) for module-centric view - at
    # hardware level
    if 17 in entries_by_type:
        memory_modules = _process_memory_modules(entries_by_type[17])
        if memory_modules:
            hardware["memory"] = memory_modules

    # Add processors at hardware level (if we processed them earlier)
    if 4 in entries_by_type and processors_data:
        hardware["processors"] = processors_data

    return hardware
