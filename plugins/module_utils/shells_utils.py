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

"""Helpers for parsing ``/etc/shells`` content."""

from __future__ import annotations

from base64 import b64decode
from typing import Any, Iterable, Sequence, Union

from ansible_collections.o0_o.utils.plugins.module_utils import strip_comments


def _coerce_to_text(data: Union[str, Sequence[str]]) -> str:
    """Convert sequence or string input to text."""
    if isinstance(data, str):
        return data

    if isinstance(data, Iterable):
        return "\n".join(str(part) for part in data)

    return ""


def parse_shells(data: Union[str, Sequence[str], dict[str, Any]]) -> list[str]:
    """Parse /etc/shells style content into a list of shell paths.

    Accepts raw strings, iterable line collections, or dictionaries that
    look like results from Ansible's slurp/command modules.

    :param data: Raw content or structured command/slurp result.
    :returns: List of shell paths (without comments or blank lines).
    """
    text = ""

    if isinstance(data, dict):
        content = data.get("content")
        stdout = data.get("stdout")

        if isinstance(content, str):
            # A read or slurp result declares its base64 encoding.
            # Only a declaration justifies decoding: shell paths are
            # themselves base64 alphabet, so /bin/sh and /bin/bash
            # together decode without complaint into five junk bytes
            if data.get("encoding") == "base64":
                text = b64decode(content).decode("utf-8")
            else:
                text = content
        elif isinstance(stdout, str):
            text = stdout
        else:
            # Attempt to treat dict values as sequence of lines
            text = _coerce_to_text(data.values())
    else:
        text = _coerce_to_text(data)

    if not text:
        return []

    cleaned = strip_comments(text)
    if not cleaned:
        return []

    shells = []
    for line in cleaned.splitlines():
        entry = line.strip()
        if entry:
            shells.append(entry)

    return shells


__all__ = ["parse_shells"]
