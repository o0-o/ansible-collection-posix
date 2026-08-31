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

"""Unit tests for dmidecode module_utils helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils.dmidecode_utils import (  # noqa: E501
    _is_meaningless_value,
    _memory_device_key,
    _parse_dmidecode,
    _process_bios,
    _process_chassis,
    _process_oem_strings,
    _process_processors,
    _process_system,
    get_dmidecode_command_requests,
    process_dmidecode_command_results,
)


@pytest.fixture
def test_data_dir() -> Path:
    """Path to test data files directory."""
    return Path(__file__).parent / "files"


@pytest.fixture
def casa_memory(test_data_dir: Path) -> dict:
    """Parse a real four DIMM board's ``dmidecode -t memory``.

    The ASRock X570 this came from carries 4 x 32 GiB across two
    channels, and prints the Locators "DIMM 0" and "DIMM 1" once in
    each.
    """
    output = (test_data_dir / "dmidecode_memory_asrock_x570.txt").read_text()
    parsed, errors = _parse_dmidecode(output, "")

    assert errors == []
    return parsed


def test_process_bios_date_parsed() -> None:
    """A parseable release date lands on the timeline."""
    bios = _process_bios({"values": {"release_date": "05/21/2021"}})

    assert bios["date"] == {
        "seconds": 1621555200,
        "pretty": "Friday, May 21, 2021",
    }


def test_process_bios_date_unparseable_nulls_seconds() -> None:
    """An unparseable release date keeps the point-in-time shape.

    The vendor's string is the only rendering available, so pretty
    carries it verbatim and seconds is null rather than missing: a
    consumer reading date.seconds gets an answer either way.
    """
    bios = _process_bios({"values": {"release_date": "10/07/2019 rev 1.2"}})

    assert bios["date"] == {
        "seconds": None,
        "pretty": "10/07/2019 rev 1.2",
    }


def test_process_bios_without_date_omits_it() -> None:
    """A BIOS entry naming no release date reports no date."""
    bios = _process_bios({"values": {"vendor": "American Megatrends Inc."}})

    assert "date" not in bios
    assert bios["make"] == "American Megatrends Inc."


def test_process_bios_without_vendor_nulls_make() -> None:
    """An absent vendor is null, the convention seconds follows."""
    bios = _process_bios({"values": {}})

    assert bios["make"] is None


def test_memory_modules_keyed_by_bank_and_locator(casa_memory: dict) -> None:
    """Every DIMM is reported, even where two banks share a Locator.

    A Locator is only unique within its bank. Keyed on the Locator
    alone, channel B overwrote channel A and this four DIMM host
    reported two.
    """
    module = casa_memory["memory"]["m391a4g43mb1-ctd"]

    assert sorted(module["locations"]) == [
        "p0 channel a/dimm 0",
        "p0 channel a/dimm 1",
        "p0 channel b/dimm 0",
        "p0 channel b/dimm 1",
    ]


def test_memory_modules_account_for_the_capacity(casa_memory: dict) -> None:
    """The modules reported add up to the capacity reported.

    The fact used to contradict itself: 128 GiB of capacity beside two
    32 GiB DIMMs, because capacity is counted from the memory array and
    the modules were counted by a colliding key.
    """
    module = casa_memory["memory"]["m391a4g43mb1-ctd"]
    installed = module["capacity"]["bytes"] * len(module["locations"])

    assert installed == casa_memory["baseboard"]["memory"]["capacity"]["bytes"]


def test_memory_locations_carry_their_own_serials(casa_memory: dict) -> None:
    """Each DIMM keeps its own serial, so none was overwritten."""
    locations = casa_memory["memory"]["m391a4g43mb1-ctd"]["locations"]
    serials = [loc["serial"] for loc in locations.values()]

    assert sorted(serials) == [
        "03C87BCF",
        "03C87C01",
        "044FA470",
        "0450F04F",
    ]


def test_memory_slots_keyed_like_the_modules(casa_memory: dict) -> None:
    """The slot view names the same devices by the same keys.

    The two views describe the same DIMMs, so a playbook correlating
    them reads one key in both.
    """
    slots = casa_memory["baseboard"]["slots"]["dimm"]

    assert sorted(slots) == sorted(
        casa_memory["memory"]["m391a4g43mb1-ctd"]["locations"]
    )
    assert slots["p0 channel a/dimm 0"]["description"] == "P0 CHANNEL A"
    assert slots["p0 channel b/dimm 0"]["description"] == "P0 CHANNEL B"


def test_memory_device_key_without_bank_uses_the_locator() -> None:
    """A board naming no bank has nothing to qualify the Locator with."""
    assert _memory_device_key({"locator": "DIMM 0"}) == "dimm 0"
    assert (
        _memory_device_key(
            {"locator": "DIMM 0", "bank_locator": "Not Specified"}
        )
        == "dimm 0"
    )


def test_memory_device_key_without_a_locator_is_none() -> None:
    """A bank alone does not name a device."""
    assert _memory_device_key({"bank_locator": "P0 CHANNEL A"}) is None


def test_processors_keyed_by_model_with_socket_locations() -> None:
    """A processor model groups the sockets that hold it.

    The way a part number groups DIMMs and each DIMM keeps its slot:
    the model states the spec once - make, family, total cores, rated
    speed - and each socket files what it alone knows beneath
    locations. The sockets view is keyed by the same designations.
    """
    processors, sockets = _process_processors(
        [
            {
                "handle": "0x0004",
                "values": {
                    "socket_designation": "AM4",
                    "manufacturer": "Advanced Micro Devices, Inc.",
                    "version": "AMD Ryzen 9 5900XT 16-Core Processor",
                    "family": "Zen",
                    "core_count": "16",
                    "core_enabled": "16",
                    "max_speed": "4900 MHz",
                    "current_speed": "3300 MHz",
                },
            }
        ],
        {},
    )

    assert list(processors) == ["amd_ryzen_9_5900xt_16_core_processor"]
    assert list(sockets) == ["am4"]
    assert sockets["am4"]["populated"] is True

    processor = processors["amd_ryzen_9_5900xt_16_core_processor"]

    assert processor["make"] == "Advanced Micro Devices, Inc."
    assert processor["model"] == {
        "name": "amd_ryzen_9_5900xt_16_core_processor",
        "pretty": "AMD Ryzen 9 5900XT 16-Core Processor",
    }
    assert processor["family"] == "Zen"
    assert processor["cores"] == {"total": 16}
    assert processor["speed"] == {
        "max": {"hertz": 4900000000, "pretty": "4.9 GHz"}
    }

    location = processor["locations"]["am4"]

    assert location["cores"] == {"enabled": 16}
    assert location["speed"] == {
        "current": {"hertz": 3300000000, "pretty": "3.3 GHz"}
    }


def test_identical_processors_share_a_record() -> None:
    """Two sockets holding one model are one spec, twice located.

    Keyed by socket, a dual-CPU host stated the same spec once per
    socket. The model is stated once now, and the serials that tell
    the two pieces of hardware apart sit in the location each socket
    owns.
    """
    entries = [
        {
            "handle": handle,
            "values": {
                "socket_designation": designation,
                "manufacturer": "Intel",
                "version": "Intel(R) Xeon(R) CPU E5-2620 v3 @ 2.40GHz",
                "serial_number": serial,
            },
        }
        for handle, designation, serial in (
            ("0x0004", "CPU1", "CPU001SERIAL001"),
            ("0x0005", "CPU2", "CPU001SERIAL002"),
        )
    ]

    processors, sockets = _process_processors(entries, {})

    assert list(processors) == ["intel_xeon_cpu_e5_2620_v3"]

    locations = processors["intel_xeon_cpu_e5_2620_v3"]["locations"]

    assert sorted(locations) == ["cpu1", "cpu2"]
    assert locations["cpu1"]["serial"] == "CPU001SERIAL001"
    assert locations["cpu2"]["serial"] == "CPU001SERIAL002"
    assert sorted(sockets) == ["cpu1", "cpu2"]
    assert sorted(sockets) == sorted(locations)


def test_hardware_names_the_command_that_answered(
    test_data_dir: Path,
) -> None:
    """The namespace says dmidecode was consulted, by name alone."""
    output = (test_data_dir / "dmidecode_memory_asrock_x570.txt").read_text()
    completed = [
        dict(
            request,
            rc=0,
            stdout=output,
            stdout_lines=output.splitlines(),
            stderr="",
            stderr_lines=[],
        )
        for request in get_dmidecode_command_requests()
    ]

    facts, errors = process_dmidecode_command_results(completed)

    assert errors == []
    assert facts["o0_hardware"]["evidence"] == {"commands": ["dmidecode"]}
    # Origins sits where evidence sits, so the section that names what
    # was consulted names who consulted it
    assert facts["o0_hardware"]["origins"] == ["o0_o.posix.dmidecode"]


def test_oem_placeholder_reads_as_absent() -> None:
    """"To Be Filled By O.E.M." is a placeholder, not an identity.

    A vendor that filled nothing in said nothing: the field reads as
    absent per each section's own convention, rather than publishing
    the placeholder as if a make, serial or asset tag had a value.
    """
    placeholder = "To Be Filled By O.E.M."

    assert _is_meaningless_value(placeholder) is True
    assert _is_meaningless_value("To Be Filled By O.E.M") is True

    system = _process_system(
        {
            "values": {
                "manufacturer": placeholder,
                "product_name": "X570 Phantom Gaming 4",
                "serial_number": placeholder,
                "sku_number": placeholder,
                "family": placeholder,
            }
        }
    )
    assert "make" not in system
    assert "serial" not in system
    assert "sku" not in system
    assert "family" not in system
    assert system["model"] == "X570 Phantom Gaming 4"

    chassis = _process_chassis(
        {
            "values": {
                "manufacturer": placeholder,
                "asset_tag": placeholder,
                "version": placeholder,
                "type": "Desktop",
            }
        }
    )
    assert "make" not in chassis
    assert "asset_tag" not in chassis
    assert "version" not in chassis
    assert chassis["type"] == "Desktop"

    oem = _process_oem_strings(
        [{"values": {"string_1": placeholder, "string_2": "real thing"}}]
    )
    assert oem == ["real thing"]


def test_bios_placeholder_vendor_is_null() -> None:
    """The BIOS section nulls an absent make, so a placeholder one
    nulls the same way."""
    bios = _process_bios(
        {"values": {"vendor": "To Be Filled By O.E.M."}}
    )

    assert bios["make"] is None


def test_voltage_bounds_named_like_speed_bounds(casa_memory: dict) -> None:
    """A boundary is min or max wherever this parser writes one.

    speed carried max while voltage carried maximum and minimum, so a
    consumer comparing the two bounds of one device spelled the same
    idea two ways.
    """
    module = casa_memory["memory"]["m391a4g43mb1-ctd"]

    assert module["voltage"] == {
        "min": {"v": 1.2, "pretty": "1.2 V"},
        "max": {"v": 1.2, "pretty": "1.2 V"},
    }
    assert list(module["speed"]) == ["max"]
