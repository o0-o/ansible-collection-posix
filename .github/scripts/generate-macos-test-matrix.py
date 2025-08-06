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

"""Generate test matrix for macOS CI based on Python-Ansible compatibility."""

import json

# Read the compatibility matrix
with open(".github/matrix/python-ansible-compatibility.json", "r") as f:
    compat = json.load(f)

# Read the macOS versions
with open(".github/matrix/macos-os.json", "r") as f:
    os_data = json.load(f)

# Generate flat matrix entries
matrix_entries = []

for os_name in os_data["os"]:
    for py_compat in compat["compatibility"]:
        python_version = py_compat["python"]
        for ansible in py_compat["ansible_versions"]:
            matrix_entries.append(
                {
                    "os": os_name,
                    "python": python_version,
                    "ansible_version": ansible["version"],
                    "ansible_package": ansible["package"],
                }
            )

# Output the matrix in GitHub Actions format
print(json.dumps(matrix_entries))
