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

from ansible_collections.o0_o.posix.plugins.module_utils.dmidecode_utils import (  # noqa: E501
    _process_bios,
)


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
