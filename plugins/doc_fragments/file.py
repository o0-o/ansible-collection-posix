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
    DOCUMENTATION = """
    options:
      owner:
        description:
          - Name of the user that should own the file.
        type: str
      group:
        description:
          - Name of the group that should own the file.
        type: str
      mode:
        description:
          - Mode to set on the file, in octal notation (e.g., C(0644)).
          - Symbolic modes (e.g., C(u+rwx)) are not supported.
        type: raw
      setype:
        description:
          - SELinux file type (e.g., C(httpd_sys_content_t)).
          - Must be a valid type string; the value C(_default) is not
            supported.
        type: str
      seuser:
        description:
          - SELinux user component (e.g., C(system_u)).
          - Must be explicitly specified; the value C(_default) is not
            supported.
        type: str
      serole:
        description:
          - SELinux role component (e.g., C(object_r)).
          - Must be explicitly specified; the value C(_default) is not
            supported.
        type: str
      selevel:
        description:
          - SELinux level (e.g., C(s0)).
          - Must be explicitly specified; the value C(_default) is not
            supported.
        type: str
      backup:
        description:
          - Create a backup copy of the file before modifying it.
          - The backup file will be placed in the same directory and include a
            timestamp and hash suffix.
        type: bool
        default: false
      validate:
        description:
          - Validation command to run against the temporary file before
            replacing the destination.
          - The command should contain a C(%s) which will be replaced with the
            path to the temporary file.
        type: str
    notes:
      - All writes are performed atomically by writing to a temporary file and
        moving it into place.
      - SELinux contexts are applied using C(semanage) and C(restorecon) if
        available, or fall back to C(chcon).
      - The value C(_default) is not supported for any SELinux parameter.
      - The C(unsafe_writes) option is not supported.
    """
