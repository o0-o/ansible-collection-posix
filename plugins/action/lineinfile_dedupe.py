# vim: ts=4:sw=4:sts=4:et:ft=python
# -*- mode: python; tab-width: 4; indent-tabs-mode: nil; -*-
#
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later
# (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
#
# Copyright (c) 2025 oØ.o (@o0-o)
#
# Adapted from:
#   - The lineinfile module in Ansible core (GPL-3.0-or-later)
#     https://github.com/ansible/ansible/blob/54ccad9e460cb6bfa0ff585a46289239966b56cc/lib/ansible/modules/lineinfile.py
#
# This file is part of the o0_o.posix Ansible Collection.

from __future__ import annotations

from ansible.errors import AnsibleError
from ansible.module_utils.common.file import get_file_arg_spec
from ansible.module_utils.common.text.converters import to_text
from ansible_collections.o0_o.posix.plugins.action_utils import PosixBase
import re


class ActionModule(PosixBase):
    """
    Insert or remove a line in a file with optional deduplication,
    and fallback support for raw mode if the Python interpreter is missing.
    """

    TRANSFERS_FILES = False
    supports_check_mode = True
    supports_diff = True

    def _ensure_line_present(self, task_vars=None):
        """
        Ensure the specified line is present in the file, with optional
        insertion, replacement, or deduplication behavior.
        """
        self._display.vvv("Ensuring line is present in file")
        self._display.vvv(f"Original lines: {self.lines}")
        self._display.vvv(f"Desired line: {self.line}")
        self._display.vvv(
            f"regexp: {self.regexp}, search_string: {self.search_string}"
        )
        self._display.vvv(
            f"insertafter: {self.insertafter}, insertbefore: "
            "{self.insertbefore}"
        )
        self._display.vvv(
            f"firstmatch: {self.firstmatch}, backrefs: {self.backrefs}, "
            f"dedupe: {self.dedupe}"
        )

        self.new_lines = self.lines[:]

        if self.create:
            self._display.vvv(
                "Creating destination parent directories (create=true)"
            )
            self._mk_dest_dir(self.path, task_vars=task_vars)
            if self.results.get('failed', False):
                self._display.vvv("Directory creation failed, aborting")
                return

        line_indices = []
        match_indices = []
        relative_insert_indices = []
        dedupe_indices = []
        match_choice = 0 if self.firstmatch else -1
        insert_index = None
        replace_index = None
        keep_index = None

        self._display.vvv("Scanning lines for matches...")

        for lineno, cur_line in enumerate(self.lines):
            if self.regexp:
                if self.re_m.search(cur_line):
                    match_indices.append(lineno)
                    self._display.vvv(
                        f"regexp match at line {lineno}: {cur_line}"
                    )

            elif self.search_string:
                if self.search_string in cur_line:
                    match_indices.append(lineno)
                    self._display.vvv(
                        f"search_string match at line {lineno}: {cur_line}"
                    )

            if self.line == cur_line:
                line_indices.append(lineno)
                self._display.vvv(f"literal match at line {lineno}")

            if self.re_ins and self.re_ins.search(cur_line):
                relative_insert_indices.append(lineno)
                self._display.vvv(
                    f"insertbefore/after match at line {lineno}: {cur_line}"
                )

        self._display.vvv(f"line_indices: {line_indices}")
        self._display.vvv(f"match_indices: {match_indices}")
        self._display.vvv(
            f"relative_insert_indices: {relative_insert_indices}"
        )

        if not line_indices:
            if not match_indices:
                if not relative_insert_indices:
                    if self.insertbefore == 'BOF':
                        insert_index = 0
                        self._display.vvv("No matches found, inserting at BOF")
                    else:
                        insert_index = len(self.new_lines)
                        self._display.vvv("No matches found, appending at EOF")
                else:
                    if self.insertafter:
                        insert_index = (
                            relative_insert_indices[match_choice] + 1
                        )
                        self._display.vvv(
                            f"insertafter match at {insert_index - 1}, "
                            "inserting at {insert_index}"
                        )
                    elif self.insertbefore:
                        insert_index = relative_insert_indices[match_choice]
                        self._display.vvv(
                            f"insertbefore match at {insert_index}"
                        )
                    else:
                        raise AnsibleError(
                            "'relative_insert_indices' should never be "
                            "populated if insertafter and insertbefore are "
                            "'None'"
                        )
            else:
                replace_index = match_indices[match_choice]
                self._display.vvv(
                    f"regex/search match at line {replace_index} for "
                    "replacement"
                )
        else:
            if relative_insert_indices:
                if self.insertbefore:
                    insertbefore_line_indices = [
                        i for i in line_indices
                        if i < relative_insert_indices[match_choice]
                    ]
                    if len(insertbefore_line_indices) > 0:
                        # Keep instance closest to insertbefore match
                        keep_index = insertbefore_line_indices[-1]
                        self._display.vvv(
                            "Exact line found before insertbefore line"
                        )
                    else:
                        insert_index = relative_insert_indices[match_choice]
                        self._display.vvv(
                            "Inserting immediately before insertbefore match"
                        )
                if self.insertafter:
                    insertafter_line_indices = [
                        i for i in line_indices
                        if i > relative_insert_indices[match_choice]
                    ]
                    if len(insertafter_line_indices) > 0:
                        # Keep instance closest to insertbefore match
                        keep_index = insertafter_line_indices[0]
                        self._display.vvv(
                            "Exact line found after insertafter line"
                        )
                    else:
                        insert_index = (
                            relative_insert_indices[match_choice] + 1
                        )
                        self._display.vvv(
                            "Inserting immediately after insertafter match"
                        )
            else:
                keep_index = line_indices[match_choice]
            if keep_index:
                self._display.vvv(
                    f"Keeping exact line already at index {keep_index}"
                )

        if insert_index is not None:
            self.new_lines.insert(insert_index, self.line)
            keep_index = insert_index
            self.results['msg'] = 'line added'
            self._display.vvv(f"Inserted line at index {insert_index}")

        elif replace_index is not None:
            match_line = self.lines[replace_index]
            if self.backrefs and self.regexp:
                match = self.re_m.search(match_line)
                expanded_line = match.expand(self.line) if match else self.line
                self._display.vvv(f"Backref expanded line: {expanded_line}")
            else:
                expanded_line = self.line

            self.new_lines[replace_index] = expanded_line
            keep_index = replace_index
            self.results['msg'] = 'line replaced'
            self._display.vvv(
                f"Replaced line at index {replace_index} with: {expanded_line}"
            )

        else:
            if keep_index:
                self._display.vvv(
                    "Line already present; no insert or replace needed"
                )

            elif not match_indices:
                self._display.vvv(
                    "No match or insertion index found, raising error"
                )
                raise AnsibleError('No lines found, added or replaced')

        if self.dedupe:
            self._display.vvv("Deduplication enabled, removing duplicates")
            for i in match_indices + line_indices:
                if i > keep_index and insert_index:
                    dedupe_indices.append(i + 1)
                elif i != keep_index:
                    dedupe_indices.append(i)
            dedupe_count = len(dedupe_indices)
            for i in sorted(dedupe_indices, reverse=True):
                self._display.vvv(
                    f"Removing duplicate at line: {self.new_lines[1]}"
                )
                del self.new_lines[i]
            self.results['msg'] += f" {dedupe_count} lines deduped"
            self._display.vvv(f"{dedupe_count} lines deduped")

    def _remove_matching_lines(self, task_vars=None):
        """
        Remove lines matching a pattern, exact line, or search string.
        """
        self.new_lines = []
        removed_count = 0

        for cur_line in self.lines:
            if (
                self.regexp and self.re_m.search(cur_line)
                or self.search_string and self.search_string in cur_line
                or self.line and cur_line.rstrip('\r\n') == self.line
            ):
                removed_count += 1  # match is found, skip this line
            else:
                self.new_lines.append(cur_line)

        self._display.vvv(f"{removed_count} lines removed")
        self.results.update({
            'found': removed_count,
            'msg': (
                f"{removed_count} line(s) removed"
                if removed_count else "no changes made"
            ),
        })

    def _audit_args(self, task_vars=None):
        """
        Validate and normalize arguments passed to the plugin.

        This includes:
        - Warning about unsafe values (e.g., empty regex)
        - Checking filesystem state with `_pseudo_stat`
        - Enforcing parameter dependencies (e.g., backrefs requires regexp)
        - Compiling regexes used for matching/insertion
        - Setting default insertion behavior if none specified

        Sets `self.re_m` and `self.re_ins` for later use.
        Updates `self.results` with failure info if validation fails.
        """
        self._display.vvv("Auditing arguments")

        # regexp and search_string
        if '' in [self.regexp, self.search_string]:
            param_name = 'search string'
            msg = (
                'The %s is an empty string, which will match every line in '
                'the file. This may have unintended consequences, such as '
                'replacing the last line in the file rather than appending.'
            )
            if self.regexp == '':
                param_name = 'regular expression'
                msg += (
                    " If this is desired, use '^' to match every line in the "
                    'file and avoid this warning.'
                )
            self._display.warning(msg % param_name)

        # Fileysystem state
        self.stat = self._pseudo_stat(self.path, task_vars=task_vars)
        self.results['raw'] = self.stat['raw']
        if self.stat['exists']:
            if self.stat['type'] != 'file':
                self.results.update({
                    'changed': False,
                    'rc': 256,
                    'msg': f"Path {self.path} is a {self.stat['type']}!",
                    'failed': True
                })
        elif not self.create:
            self.results.update({
                'changed': False,
                'rc': 257,
                'msg': f"Destination {self.path} does not exist!",
                'failed': True
            })

        # Argument dependencies
        if self.state == 'present':
            if self.backrefs and not self.regexp:
                self.results.update({
                    'msg': 'regexp is required with backrefs=true',
                    'failed': True,
                })
            if not self.line:
                self.results.update({
                    'msg': 'line is required with state=present',
                    'failed': True,
                })
            if not self.insertafter and not self.insertbefore:
                self.insertafter = 'EOF'
        else:
            if all(
                not p for p in [
                    self.regexp, self.search_string, self.line
                ]
            ):
                self.results.update({
                    'msg': (
                        'one of line, search_string, or regexp is required '
                        'with state=absent'
                    ),
                    'failed': True
                })

        # Regex, insertafter and insertbefore
        if self.regexp:
            try:
                self.re_m = re.compile(self.regexp)
            except Exception as e:
                return {
                    'failed': True,
                    'msg': f"Invalid regexp pattern: {self.regexp}: {e}"
                }

        self.re_ins = None

        if self.insertafter not in (None, 'BOF', 'EOF'):
            try:
                self.re_ins = re.compile(self.insertafter)
            except Exception as e:
                return {
                    'failed': True,
                    'msg': (
                        f"Invalid insertafter pattern: {self.insertafter}: {e}"
                    )
                }

        elif self.insertbefore not in (None, 'BOF'):
            try:
                self.re_ins = re.compile(self.insertbefore)
            except Exception as e:
                return {
                    'failed': True,
                    'msg': (
                        "Invalid insertbefore pattern: "
                        f"{self.insertbefore}: {e}"
                    )
                }

    def _read_file(self, task_vars=None):
        """
        Read the contents of the target file into `self.lines`, using either
        the Python `slurp` module or a raw fallback.

        Raises:
            AnsibleError: If the file could not be read.
        """
        self._display.vvv(f"Reading file: {self.path}")
        self.lines = []

        if self.stat['exists']:
            slurp_results = self._slurp(self.path, task_vars=task_vars)
            if slurp_results.get('failed', False):
                raise AnsibleError(
                    f"Could not read contents of file '{self.path}': "
                    f"{slurp_results['msg']}"
                )
            self.lines = slurp_results['content'].splitlines()

    def _def_args(self):
        """
        Define and parse module arguments using the file argument spec,
        and store validated values as instance attributes.

        Returns:
            dict: The validated argument dictionary.
        """
        self._display.vvv("Defining argument spec")
        argument_spec = get_file_arg_spec()
        argument_spec.pop('attributes')
        argument_spec.update(dict(
            path=dict(
                type='path',
                required=True,
                aliases=['dest', 'destfile', 'name']
            ),
            regexp=dict(type='str', aliases=['regex']),
            search_string=dict(type='str'),
            state=dict(
                type='str',
                choices=['absent', 'present'],
                default='present'
            ),
            line=dict(type='str', aliases=['value']),
            backrefs=dict(type='bool', default=False),
            insertafter=dict(type='str'),
            insertbefore=dict(type='str'),
            create=dict(type='bool', default=False),
            backup=dict(type='bool', default=False),
            firstmatch=dict(type='bool', default=False),
            dedupe=dict(type='bool', default=True),
            validate=dict(type='str'),
            _force_raw=dict(type='bool', default=False),
        ))
        mutually_exclusive = [
            ['insertbefore', 'insertafter'],
            ['regexp', 'search_string'],
            ['backrefs', 'search_string']
        ]

        validation_result, new_module_args = self.validate_argument_spec(
            argument_spec=argument_spec,
            mutually_exclusive=mutually_exclusive
        )

        self.path = new_module_args['path']
        self.state = new_module_args['state']
        self.regexp = new_module_args['regexp']
        self.search_string = new_module_args['search_string']
        self.line = new_module_args['line']
        self.backrefs = new_module_args['backrefs']
        self.insertafter = new_module_args['insertafter']
        self.insertbefore = new_module_args['insertbefore']
        self.create = new_module_args['create']
        self.backup = new_module_args['backup']
        self.firstmatch = new_module_args['firstmatch']
        self.validate = new_module_args['validate']
        self.dedupe = new_module_args.pop('dedupe')
        self.force_raw = new_module_args.pop('_force_raw')

        self.perms = {key: new_module_args[key] for key in (
            'owner', 'group', 'mode', 'selevel', 'serole', 'setype', 'seuser'
        )}

        return new_module_args

    def run(self, tmp=None, task_vars=None):
        """
        Main entry point for the action plugin.

        Performs its own line presence/removal logic with raw fallback support,
        including reading, editing, and writing the file using POSIX-safe
        methods.

        Returns:
            dict: Standard Ansible result dictionary.
        """
        self._display.vvv("Starting lineinfile_dedupe run()")
        task_vars = task_vars or {}
        self._supports_async = False

        new_module_args = self._def_args()
        self._display.vvv(f"new_module_args: {new_module_args}")

        self.results = super(ActionModule, self).run(tmp, task_vars=task_vars)
        self.results.update({
            'invocation': self._task.args.copy(),
            'changed': False,
            'raw': False,
            'msg': '',
        })
        del tmp  # tmp is unused

        self._audit_args(task_vars=task_vars)
        if not self.results.get('failed', False):

            self._read_file(task_vars=task_vars)

            if self.state == 'present':
                self._ensure_line_present(task_vars=task_vars)
            else:
                self._remove_matching_lines(task_vars=task_vars)

            if not self.results.get('failed', False):
                try:
                    changed = self.results['changed']
                    write_results = self._write_file(
                        content=self.new_lines,
                        dest=self.path,
                        perms=self.perms,
                        backup=self.backup,
                        validate_cmd=self.validate,
                        check_mode=self._task.check_mode,
                        task_vars=task_vars,
                    )
                    self.results.update(write_results)
                    # This is not really necessary, but worth
                    # keeping in mind in case things change in the
                    # future.
                    self.results['changed'] |= changed
                except Exception as e:
                    self.results.update({
                        'failed': True,
                        'msg': f"Failed to write file: {to_text(e)}"
                    })

        # Clean up temporary files
        self._remove_tmp_path(self._connection._shell.tmpdir)

        return self.results
