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

"""Tests for the dmidecode filter wrapper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from ansible.errors import AnsibleFilterError

from ansible_collections.o0_o.posix.plugins.filter import (
    dmidecode as dmidecode_mod,
)
from ansible_collections.o0_o.posix.plugins.filter.dmidecode import (
    FilterModule,
)


@pytest.fixture
def filter_module() -> FilterModule:
    """Provide a filter instance per test."""
    return FilterModule()


@pytest.fixture
def test_data_dir() -> Path:
    """Path to test data files directory."""
    return Path(__file__).parent / "files"


def test_dmidecode_filter_exposes_helper(filter_module: FilterModule) -> None:
    """filters() advertises the dmidecode callable."""
    filters = filter_module.filters()
    assert set(filters) == {"dmidecode"}


def test_dmidecode_filter_delegates_to_helper(
    filter_module: FilterModule,
) -> None:
    """Wrapper returns data from _parse_dmidecode unchanged."""
    expected = [{"handle": "0x0000", "type": 0}]
    with patch.object(
        dmidecode_mod,
        "_parse_dmidecode",
        return_value=(expected, []),
    ) as mock_parse:
        result = filter_module.filters()["dmidecode"]("dmidecode output")

    mock_parse.assert_called_once_with("dmidecode output", "")
    assert result is expected


@pytest.mark.parametrize("error", [ValueError("bad"), ImportError("missing")])
def test_dmidecode_filter_wraps_parse_errors(
    filter_module: FilterModule,
    error: Exception,
) -> None:
    """Test that parse errors become AnsibleFilterError."""
    with patch.object(
        dmidecode_mod,
        "_parse_dmidecode",
        return_value=(None, [error]),
    ):
        with pytest.raises(AnsibleFilterError, match="dmidecode failed"):
            filter_module.filters()["dmidecode"]("broken")


def test_dmidecode_parses_real_output(
    filter_module: FilterModule, test_data_dir: Path
) -> None:
    """Test parsing real dmidecode output from file."""
    dmidecode_output = (test_data_dir / "dmidecode_sample_1.txt").read_text()

    result = filter_module.filters()["dmidecode"](dmidecode_output)

    # Verify we got a structured hardware dict
    assert isinstance(result, dict)

    # Check system information at top level
    assert result["make"] == "Supermicro"
    assert result["model"] == "SSG-6028R-E1CR24L-IN001"
    assert "serial" in result
    assert "uuid" in result

    # Check OEM strings
    assert "oem" in result
    assert isinstance(result["oem"], list)
    assert len(result["oem"]) == 2
    assert result["oem"][0] == "Intel Haswell/Wellsburg/Grantley"
    assert result["oem"][1] == "Supermicro motherboard-X10 Series"

    # Check boot status
    assert "status" in result
    assert result["status"] == "No errors detected"

    # Check power supplies (grouped by model)
    assert "power" in result
    power_supplies = result["power"]
    assert isinstance(power_supplies, dict)
    assert "supermicro_pws-1k62a-1r" in power_supplies
    psu_model = power_supplies["supermicro_pws-1k62a-1r"]
    assert psu_model["make"] == "SUPERMICRO"
    assert psu_model["model"] == "PWS-1K62A-1R"
    assert "capacity" in psu_model
    assert psu_model["capacity"]["watts"] == 1600
    assert psu_model["capacity"]["pretty"] == "1.6 kW"
    assert psu_model["type"] == "Switching"
    assert psu_model["range"] == "Auto-switch"
    assert psu_model["hotswap"] is True
    assert "locations" in psu_model
    assert isinstance(psu_model["locations"], dict)
    assert len(psu_model["locations"]) == 2
    # Check first location (PSU1)
    assert "psu1" in psu_model["locations"]
    psu1 = psu_model["locations"]["psu1"]
    assert psu1["group"] == "1"
    assert psu1["serial"] == "PSU001SERIAL001"
    assert psu1["revision"] == "1.1"
    assert psu1["status"] == "Present, OK"
    assert psu1["powered"] is True
    # Check second location (PSU2)
    assert "psu2" in psu_model["locations"]
    psu2 = psu_model["locations"]["psu2"]
    assert psu2["group"] == "2"
    assert psu2["serial"] == "PSU001SERIAL002"

    # Check memory modules at hardware level
    assert "memory" in result
    memory_modules = result["memory"]
    assert isinstance(memory_modules, dict)
    assert "m386a4g40dm0-cpb" in memory_modules
    module = memory_modules["m386a4g40dm0-cpb"]
    assert module["make"] == "Samsung"
    assert module["model"] == "M386A4G40DM0-CPB"
    assert "bits" in module
    assert module["bits"]["data"] == 64
    assert module["bits"]["total"] == 72
    assert "ecc" in module
    assert module["ecc"] is True  # 72 bits = ECC (multiple of 8, not 32)
    assert "capacity" in module
    assert module["capacity"]["bytes"] == 34359738368
    assert module["capacity"]["pretty"] == "32 GiB"
    assert "speed" in module
    assert "max" in module["speed"]
    assert module["speed"]["max"]["transfers/s"] == 2133000000
    assert module["speed"]["max"]["pretty"] == "2.13 GT/s"  # SI normalized
    assert module["rank"] == 4
    assert "locations" in module
    assert isinstance(module["locations"], dict)
    assert "p2-dimme1" in module["locations"]
    location = module["locations"]["p2-dimme1"]
    assert location["serial"] == "MEM001SERIAL003"
    assert "speed" in location
    assert location["speed"]["transfers/s"] == 1866000000
    assert location["speed"]["pretty"] == "1.87 GT/s"  # SI normalized
    assert location["tag"] == "P2-DIMME1_AssetTag (date:15/18)"

    # Check chassis information
    assert "chassis" in result
    chassis = result["chassis"]
    assert chassis["make"] == "Supermicro"
    assert "serial" in chassis
    assert isinstance(chassis["lock"], bool)
    assert chassis["boot"] == "Safe"
    assert chassis["psu"] == "Safe"
    assert chassis["thermal"] == "Safe"

    # Check baseboard information
    assert "baseboard" in result
    baseboard = result["baseboard"]
    assert baseboard["make"] == "Supermicro"
    assert baseboard["model"] == "X10DSC+"
    assert baseboard["version"]["id"] == "1.01"
    assert "serial" in baseboard

    # Check memory information in baseboard
    assert "memory" in baseboard
    memory = baseboard["memory"]
    assert memory["type"] == "DDR4"
    assert memory["synchronous"] is True
    assert memory["ecc"] == "multi-bit"
    assert "capacity" in memory
    assert memory["capacity"]["bytes"] == 1649267441664
    assert memory["capacity"]["pretty"] == "1.5 TiB"
    # Form factor not included (captured by slot type key)

    # Check BIOS information
    assert "bios" in baseboard
    bios = baseboard["bios"]
    assert bios["make"] == "American Megatrends Inc."
    assert "version" in bios
    assert "id" in bios["version"]
    assert "date" in bios
    assert "pretty" in bios["date"]
    assert "seconds" in bios["date"]
    assert "features" in bios
    assert isinstance(bios["features"], list)

    # Check interfaces (all keys are lowercase)
    if "interfaces" in baseboard:
        assert isinstance(baseboard["interfaces"], dict)
        # Check that J1A1 becomes j1a1 with nested lowercase keys
        if "j1a1" in baseboard["interfaces"]:
            assert isinstance(baseboard["interfaces"]["j1a1"], dict)
            # PS2Mouse becomes ps2mouse
            if "ps2mouse" in baseboard["interfaces"]["j1a1"]:
                assert "type" in baseboard["interfaces"]["j1a1"]["ps2mouse"]

    # Check IPMI information
    assert "ipmi" in baseboard
    ipmi = baseboard["ipmi"]
    assert "version" in ipmi
    assert ipmi["version"]["id"] == "2.0"

    # Check onboard devices
    assert "devices" in baseboard
    devices = baseboard["devices"]
    assert isinstance(devices, dict)
    assert "aspeed_video_ast2400" in devices
    gpu = devices["aspeed_video_ast2400"]
    assert gpu["type"] == "video"
    assert gpu["enabled"] is True
    assert gpu["bus"] == "0000:08:00.0"

    # Check sockets
    assert "sockets" in baseboard
    sockets = baseboard["sockets"]
    assert isinstance(sockets, dict)
    assert sockets["type"] == "LGA2011-3"
    assert "cpu1" in sockets
    assert sockets["cpu1"]["populated"] is True
    assert "cpu2" in sockets
    assert sockets["cpu2"]["populated"] is True

    # Check processors at hardware level
    assert "processors" in result
    processors = result["processors"]
    assert isinstance(processors, dict)
    # Model key is normalized from version string (trademark symbols removed)
    assert "intel_xeon_cpu_e5_2620_v3" in processors
    proc = processors["intel_xeon_cpu_e5_2620_v3"]
    assert proc["make"] == "Intel"
    assert proc["family"] == "Xeon"
    # Model is cleaned: trademark symbols, @ speed, make, family,
    # and CPU removed
    assert proc["model"] == "E5-2620 v3"
    # Signature is in individual locations, not in processor spec
    assert "signature" not in proc
    # Check cores (threads excluded due to DMI ambiguity)
    assert "cores" in proc
    assert proc["cores"]["total"] == 6
    assert "threads" not in proc
    # Check speed
    assert "speed" in proc
    assert proc["speed"]["max"]["hertz"] == 4000000000
    assert proc["speed"]["max"]["pretty"] == "4 GHz"
    # Check voltage (only present if SI utils parses it)
    if "voltage" in proc:
        assert "v" in proc["voltage"]
        assert "pretty" in proc["voltage"]
    # Check external clock (flattened)
    assert "clock" in proc
    assert proc["clock"]["hertz"] == 100000000
    assert proc["clock"]["pretty"] == "100 MHz"
    # Check features as dict with abbreviation: description
    assert "features" in proc
    assert isinstance(proc["features"], dict)
    assert "FPU" in proc["features"]
    assert proc["features"]["FPU"] == "Floating-point unit on-chip"
    assert "VME" in proc["features"]
    assert proc["features"]["VME"] == "Virtual mode extension"
    # Check characteristics
    assert "characteristics" in proc
    assert isinstance(proc["characteristics"], list)
    assert "64-bit capable" in proc["characteristics"]
    assert "Multi-Core" in proc["characteristics"]
    # Cache is now in individual locations (socket-specific)
    assert "cache" not in proc
    # Check locations
    assert "locations" in proc
    assert isinstance(proc["locations"], dict)
    assert "cpu1" in proc["locations"]
    cpu1 = proc["locations"]["cpu1"]
    # Check signature (now in location, not processor spec)
    assert "signature" in cpu1
    assert cpu1["signature"]["type"] == 0
    assert cpu1["signature"]["family"] == 6
    assert cpu1["signature"]["model"] == 63
    assert cpu1["signature"]["stepping"] == 2
    assert cpu1["cores"]["enabled"] == 6
    assert "speed" in cpu1
    assert cpu1["speed"]["hertz"] == 2400000000
    assert cpu1["speed"]["pretty"] == "2.4 GHz"
    # Check cache (internal caches now in individual locations)
    assert "cache" in cpu1
    cache = cpu1["cache"]
    assert isinstance(cache, dict)
    # Check L1 cache
    assert "l1" in cache
    l1 = cache["l1"]
    assert "capacity" in l1
    assert (
        l1["capacity"]["bytes"] == 384000
    )  # SI utils parses "384 kB" as decimal
    assert l1["capacity"]["pretty"] == "384 kB"
    # type excluded for L1 (was "Other")
    assert "type" not in l1
    assert l1["mode"] == "Write Back"
    assert l1["parity"] is True
    assert "ecc" not in l1
    assert l1["associativity"] == 8
    assert l1["enabled"] is True
    # Check L2 cache
    assert "l2" in cache
    l2 = cache["l2"]
    assert l2["capacity"]["bytes"] == 1536000  # SI utils parses "1536 kB"
    assert l2["capacity"]["pretty"] == "1.54 MB"
    assert l2["type"] == "Unified"
    assert l2["mode"] == "Write Back"
    assert l2["ecc"] is True
    assert "parity" not in l2
    assert l2["associativity"] == 8
    assert l2["enabled"] is True
    # Check L3 cache
    assert "l3" in cache
    l3 = cache["l3"]
    assert l3["capacity"]["bytes"] == 15000000  # SI utils parses "15 MB"
    assert l3["capacity"]["pretty"] == "15 MB"
    assert l3["type"] == "Unified"
    assert l3["mode"] == "Write Back"
    assert l3["ecc"] is True
    assert "parity" not in l3
    assert l3["associativity"] == 20
    assert l3["enabled"] is True
    assert "cpu2" in proc["locations"]
    cpu2 = proc["locations"]["cpu2"]
    assert cpu2["cores"]["enabled"] == 6

    # Check slots - now grouped by type, then by index
    if "slots" in baseboard:
        assert isinstance(baseboard["slots"], dict)
        # Check DIMM slots (normalized to lowercase "dimm")
        if "dimm" in baseboard["slots"]:
            dimm_slots = baseboard["slots"]["dimm"]
            assert isinstance(dimm_slots, dict)
            assert len(dimm_slots) == 24  # 12 per array × 2 arrays
            # Check populated and unpopulated
            populated = [k for k, v in dimm_slots.items() if v["populated"]]
            unpopulated = [
                k for k, v in dimm_slots.items() if not v["populated"]
            ]
            assert len(populated) == 4
            assert len(unpopulated) == 20
            # Check first slot structure (lowercase key)
            assert "p1-dimma1" in dimm_slots
            slot = dimm_slots["p1-dimma1"]
            assert slot["description"] == "P0_Node0_Channel0_Dimm0"
            assert slot["populated"] is True
            # Type is not in individual slots (defined at memory level)
            assert "type" not in slot
        # Check expansion slots (normalized to "pci_express" etc.)
        pci_slot_types = [k for k in baseboard["slots"] if "pci" in k]
        if pci_slot_types:
            pci_slots = baseboard["slots"][pci_slot_types[0]]
            assert isinstance(pci_slots, dict)
            # Check for descriptive key (e.g., "cpu2_slot1")
            descriptive_keys = [k for k in pci_slots.keys() if "cpu" in k]
            if descriptive_keys:
                # Descriptive keys are used
                slot = pci_slots[descriptive_keys[0]]
                assert "type" in slot
                assert "populated" in slot
            else:
                # Fallback to numeric IDs
                first_key = list(pci_slots.keys())[0]
                slot = pci_slots[first_key]
                assert "type" in slot
                assert "populated" in slot


def test_dmidecode_cleans_features() -> None:
    """Test that feature strings are properly cleaned."""
    from ansible_collections.o0_o.posix.plugins.module_utils.dmidecode_utils import (  # noqa: E501
        _clean_feature,
    )

    # Test removing "is supported"
    assert _clean_feature("PCI is supported") == "PCI"
    assert _clean_feature("ACPI is supported") == "ACPI"

    # Test removing "is provided"
    assert _clean_feature("3.3 V is provided") == "3.3 V"

    # Test removing "services"
    assert (
        _clean_feature("8042 keyboard services (int 9h)")
        == "8042 keyboard (int 9h)"
    )
    assert _clean_feature("Serial services (int 14h)") == "Serial (int 14h)"

    # Test preserving parens without suffixes
    assert _clean_feature("Boot from CD (int 13h)") == "Boot from CD (int 13h)"


def test_dmidecode_validates_meaningless_values() -> None:
    """Test that meaningless values are properly detected."""
    from ansible_collections.o0_o.posix.plugins.module_utils.dmidecode_utils import (  # noqa: E501
        _is_meaningless_value,
    )

    # Test common meaningless strings (case-insensitive)
    assert _is_meaningless_value("Default string") is True
    assert _is_meaningless_value("default string") is True
    assert _is_meaningless_value("Other") is True
    assert _is_meaningless_value("None") is True
    assert _is_meaningless_value("Not Specified") is True
    assert _is_meaningless_value("not specified") is True
    assert _is_meaningless_value("Unspecified") is True
    assert _is_meaningless_value("Unknown") is True
    assert _is_meaningless_value("Not Available") is True
    assert _is_meaningless_value("N/A") is True

    # Test sequential digits
    assert _is_meaningless_value("0123456789") is True
    assert _is_meaningless_value("123456789") is True

    # Test valid values
    assert _is_meaningless_value("Supermicro") is False
    assert _is_meaningless_value("X10DSC+") is False
    assert _is_meaningless_value("Safe") is False


def test_dmidecode_parses_presence() -> None:
    """Test that presence strings are converted to booleans."""
    from ansible_collections.o0_o.posix.plugins.module_utils.dmidecode_utils import (  # noqa: E501
        _parse_presence,
    )

    # Test case-insensitive boolean conversion
    assert _parse_presence("Present") is True
    assert _parse_presence("present") is True
    assert _parse_presence("Not Present") is False
    assert _parse_presence("not present") is False

    # Test passthrough for other values
    assert _parse_presence("Unknown") == "Unknown"
    assert _parse_presence("Other") == "Other"


def test_dmidecode_parses_slot_usage() -> None:
    """Test that slot usage strings are converted to booleans."""
    from ansible_collections.o0_o.posix.plugins.module_utils.dmidecode_utils import (  # noqa: E501
        _parse_slot_usage,
    )

    # Test case-insensitive boolean conversion
    assert _parse_slot_usage("In Use") is True
    assert _parse_slot_usage("in use") is True
    assert _parse_slot_usage("Available") is False
    assert _parse_slot_usage("available") is False
    assert _parse_slot_usage("Unavailable") is False

    # Test exclusion for other values
    assert _parse_slot_usage("Unknown") is None
    assert _parse_slot_usage("Other") is None


def test_dmidecode_parses_slot_length() -> None:
    """Test that slot length strings are converted to booleans."""
    from ansible_collections.o0_o.posix.plugins.module_utils.dmidecode_utils import (  # noqa: E501
        _parse_slot_length,
    )

    # Test case-insensitive boolean conversion
    assert _parse_slot_length("Short") is True
    assert _parse_slot_length("short") is True
    assert _parse_slot_length("Long") is False
    assert _parse_slot_length("long") is False

    # Test exclusion for other values
    assert _parse_slot_length("Unknown") is None
    assert _parse_slot_length("Other") is None


def test_dmidecode_parses_yes_no() -> None:
    """Test that yes/no strings are converted to booleans."""
    from ansible_collections.o0_o.posix.plugins.module_utils.dmidecode_utils import (  # noqa: E501
        _parse_yes_no,
    )

    # Test case-insensitive boolean conversion
    assert _parse_yes_no("Yes") is True
    assert _parse_yes_no("yes") is True
    assert _parse_yes_no("No") is False
    assert _parse_yes_no("no") is False

    # Test exclusion for other values
    assert _parse_yes_no("Unknown") is None
    assert _parse_yes_no("Maybe") is None


def test_dmidecode_normalizes_slot_types() -> None:
    """Test that slot types are normalized to lowercase with underscores."""
    from ansible_collections.o0_o.posix.plugins.module_utils.dmidecode_utils import (  # noqa: E501
        _normalize_slot_type,
    )

    # Test PCI Express slot normalization (removes numbers)
    assert _normalize_slot_type("x8 PCI Express 3 x8") == "pci_express"
    assert _normalize_slot_type("x16 PCI Express 3") == "pci_express"

    # Test DIMM normalization
    assert _normalize_slot_type("DIMM") == "dimm"

    # Test other slot types
    assert _normalize_slot_type("PCI Express") == "pci_express"
    # "32-bit" contains digits so entire word is removed
    assert _normalize_slot_type("32-bit PCI") == "pci"


def test_dmidecode_parses_bios_language(
    filter_module: FilterModule, test_data_dir: Path
) -> None:
    """Test BIOS language information parsing from Type 13."""
    sample_file = test_data_dir / "dmidecode_sample_2.txt"
    dmidecode_output = sample_file.read_text()

    result = filter_module.filters()["dmidecode"](dmidecode_output)

    assert "baseboard" in result
    assert "bios" in result["baseboard"]
    bios = result["baseboard"]["bios"]

    # Check languages dict structure
    assert "languages" in bios
    languages = bios["languages"]
    assert isinstance(languages, dict)
    # Check that en|US|iso8859-1 is present and enabled
    assert "en|US|iso8859-1" in languages
    assert languages["en|US|iso8859-1"]["enabled"] is True


def test_dmidecode_parses_config_options(
    filter_module: FilterModule, test_data_dir: Path
) -> None:
    """Test System Configuration Options parsing from Type 12."""
    sample_file = test_data_dir / "dmidecode_sample_3.txt"
    dmidecode_output = sample_file.read_text()

    result = filter_module.filters()["dmidecode"](dmidecode_output)

    # Check config options
    assert "config" in result
    config = result["config"]
    assert isinstance(config, list)
    assert len(config) == 1
    assert config[0] == "J1: 1-2 Normal Mode, 2-3 Recovery Mode"
