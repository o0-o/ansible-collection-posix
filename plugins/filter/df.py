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

from __future__ import annotations

from typing import Any, Dict, List, Union

from ansible_collections.o0_o.posix.plugins.filter_utils import JCBase


class FilterModule(JCBase):
    """Filter for parsing df command output using jc."""

    def filters(self) -> Dict[str, Any]:
        """Return the filter functions."""
        return {
            "df": self.df,
        }

    def _format_as_facts(
        self, parsed: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Format parsed df data for Ansible facts structure.

        :param parsed: List of filesystem dictionaries from jc
        :returns: Facts structure with filesystems keyed by mount point
        """
        filesystems = {}
        for entry in parsed:
            # Make a copy to avoid modifying the original
            entry_copy = entry.copy()
            mount_point = entry_copy.pop("mounted_on", None)
            if mount_point:
                filesystems[mount_point] = entry_copy

        return {"filesystems": filesystems}

    def df(
        self,
        data: Union[str, List[str], Dict[str, Any]],
        facts: bool = False,
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """Parse df output into structured data using jc.

        :param data: Output from df command - string, list of lines,
            or command result
        :param facts: If True, format for direct merge into Ansible facts
        :returns: List of filesystem dictionaries from jc, or facts structure
        """
        # Get parsed data from jc
        parsed = self.parse_command(data, "df")

        if not facts:
            # Return jc's parsed format directly
            return parsed

        # Format for facts module
        return self._format_as_facts(parsed)
