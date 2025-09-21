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

"""Sphinx configuration for the o0_o.posix documentation site."""

from __future__ import annotations

project = "o0_o.posix"
html_title = "o0_o.posix documentation"
html_short_title = "o0_o.posix"
html_baseurl = "https://o0-o.github.io/ansible-collection-posix/"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.githubpages",
    "sphinx_antsibull_ext",
]

pygments_style = "ansible"
highlight_language = "YAML+Jinja"

html_theme = "sphinx_ansible_theme"
html_show_sphinx = False
html_use_smartypants = True
html_use_modindex = False
html_use_index = False
html_copy_source = False

intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
    "jinja2": ("https://jinja.palletsprojects.com/en/stable/", None),
    "ansible_devel": ("https://docs.ansible.com/ansible/devel/", None),
}

default_role = "any"
nitpicky = True

exclude_patterns = [
    "_build",
    "build",
]
