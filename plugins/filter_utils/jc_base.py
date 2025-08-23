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

"""JC base class for jc-based filters."""

from __future__ import annotations

import traceback
from typing import Any, Dict, List, Union

from ansible.errors import AnsibleFilterError

try:
    import jc

    HAS_JC = True
    JC_IMPORT_ERROR = None
except ImportError:
    HAS_JC = False
    JC_IMPORT_ERROR = traceback.format_exc()


class JCBase:
    """Base class for filters that use the jc library for parsing."""

    def jc(
        self,
        data: Union[str, List[str], Dict[str, Any]],
        parser: str,
        raw: bool = False,
        quiet: bool = False,
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """Parse command output using jc library.

        :param data: Output from command - string, list of lines,
            or command result
        :param parser: Name of the jc parser to use (e.g., 'mount',
            'df', 'ps')
        :param raw: If True, return raw parsed output without
            post-processing
        :param quiet: If True, suppress jc parsing warnings
        :returns: Parsed data structure (list or dict depending on
            parser)
        :raises AnsibleFilterError: If jc is not available or parsing
            fails
        """
        # Check for jc availability
        if not HAS_JC:
            raise AnsibleFilterError(
                "The jc library is required for jc-based filters. "
                "Install it with: pip install jc",
                orig_exc=JC_IMPORT_ERROR,
            )

        # Check validity of the parser name
        jc_parsers = sorted(jc.parser_mod_list())
        if parser not in jc_parsers:
            raise AnsibleFilterError(
                f"jc parser '{parser}' not found. "
                f"Available parsers: {', '.join(jc_parsers)}"
            )

        # Extract raw output
        raw_output = self._extract_output(data)

        try:
            # Parse using jc library
            return jc.parse(parser, raw_output, raw=raw, quiet=quiet)
        except Exception as e:
            # jc raises various exceptions, catch them all
            raise AnsibleFilterError(f"Error parsing {parser}: {e}")

    def _extract_output(self, data: Union[str, List[str], Dict[str, Any]]) -> str:
        """Extract raw string output from various input formats.

        :param data: Input data in various formats
        :returns: Raw string output
        """
        if isinstance(data, dict):
            return data.get("stdout", "")
        elif isinstance(data, str):
            return data
        elif isinstance(data, list):
            return "\n".join(data)
        elif data is None:
            return ""
        else:
            return ""

    def parse_command(
        self, data: Union[str, List[str], Dict[str, Any]], parser: str
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """Parse command output using the specified jc parser.

        This is a convenience method for subclasses.

        :param data: Output from command
        :param parser: Name of the jc parser to use
        :returns: Parsed data structure
        """
        return self.jc(data, parser)
