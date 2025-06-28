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

class ModuleDocFragment:
    DOCUMENTATION = r'''
    options:
      _force_raw:
        description:
          - Force fallback to raw execution mode, bypassing native Python behavior
            even if available.
          - Intended for testing and debugging fallback logic.
        type: bool
        default: false
        required: false
    '''
