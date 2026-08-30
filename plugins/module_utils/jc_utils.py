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

"""JC parsing utilities."""

from __future__ import annotations

from typing import Any, Callable, Optional, Union

from ansible_collections.o0_o.posix.plugins.module_utils.filter_utils import (
    process_registered_result,
)

try:
    import jc

    HAS_JC = True
except ImportError:
    HAS_JC = False


def jc_parse(
    parser: str,
    data: Union[str, dict[str, Any]],
    quiet: bool = True,
    raw: bool = False,
    normalize: Optional[Callable[[str], str]] = None,
) -> Union[list[dict[str, Any]], dict[str, Any]]:
    """Parse command output using jc library.

    Handles both string and dict inputs (e.g., from command module).
    Parameter order matches jc.parse for consistency.

    A caller whose format has a spelling jc will not read passes a
    ``normalize`` to reconcile it. It runs on the content jc is about
    to be handed, which is after a registered result has been decoded,
    so an encoded blob is never what gets rewritten.

    :param parser: Name of the jc parser to use
    :param data: Command output as string or dict
    :param quiet: If True, suppress jc parsing warnings (default: True)
    :param raw: If True, return raw parsed output without
                post-processing
    :param normalize: Applied to the decoded content before jc reads
                it
    :returns: Parsed data structure (list or dict depending on
              parser)
    :raises ValueError: If parsing fails
    :raises ImportError: If jc is not available
    """
    if not HAS_JC:
        raise ImportError(
            "The jc library is required for jc parsing. "
            "Install it with: pip install jc"
        )

    # Check validity of the parser name
    jc_parsers = sorted(jc.parser_mod_list())
    if parser not in jc_parsers:
        raise ValueError(
            f"jc parser '{parser}' not found. "
            f"Available parsers: {', '.join(jc_parsers)}"
        )

    # Define the parsing function
    def parse_content(
        content: str,
    ) -> Union[list[dict[str, Any]], dict[str, Any]]:
        if normalize is not None and isinstance(content, str):
            content = normalize(content)
        try:
            # Parse using jc library
            return jc.parse(parser, content, raw=raw, quiet=quiet)
        except Exception as e:
            # jc raises various exceptions, catch them all
            raise ValueError(f"Error parsing {parser}: {e}") from e

    # Handle dict input (e.g., from command module)
    if isinstance(data, dict):
        # Use shared utility for registered result processing
        return process_registered_result(data, parse_content)

    # Parse command output string directly
    return parse_content(data)
