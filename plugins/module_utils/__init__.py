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

"""Module utilities for the o0_o.posix collection."""

from __future__ import annotations

from ansible_collections.o0_o.posix.plugins.module_utils.filter_utils import (
    process_registered_result,
)
from ansible_collections.o0_o.posix.plugins.module_utils.fstab_utils import (
    fstab,
    parse_fstab,
    parse_fstab_entry,
    generate_fstab,
    generate_fstab_entry,
)
from ansible_collections.o0_o.posix.plugins.module_utils.mount_utils import (
    mount,
    parse_mount,
    parse_mount_entry,
)
from ansible_collections.o0_o.posix.plugins.module_utils.jc_base import JCBase
from ansible_collections.o0_o.posix.plugins.module_utils.posix_action_base import (
    PosixActionBase,
)
from ansible_collections.o0_o.posix.plugins.module_utils.storage_base import (
    StorageBase,
)
from ansible_collections.o0_o.posix.plugins.module_utils.storage_drivers import (
    STORAGE_DRIVERS,
)

__all__ = [
    "JCBase",
    "PosixActionBase",
    "StorageBase",
    "STORAGE_DRIVERS",
    "fstab",
    "parse_fstab",
    "parse_fstab_entry",
    "generate_fstab",
    "generate_fstab_entry",
    "mount",
    "parse_mount",
    "parse_mount_entry",
    "process_registered_result",
]
