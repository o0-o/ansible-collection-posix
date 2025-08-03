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

import os
import shutil
import stat
import tempfile
from typing import Any, Dict, Optional

from jinja2.defaults import (
    BLOCK_END_STRING,
    BLOCK_START_STRING,
    COMMENT_END_STRING,
    COMMENT_START_STRING,
    VARIABLE_END_STRING,
    VARIABLE_START_STRING,
)

from ansible import constants as C
from ansible.errors import AnsibleActionFail, AnsibleError
from ansible.module_utils.common.file import get_file_arg_spec
from ansible.module_utils.common.text.converters import to_bytes, to_text
from ansible.template import generate_ansible_template_vars, trust_as_template
from ansible_collections.o0_o.posix.plugins.action_utils import PosixBase


class ActionModule(PosixBase):
    """
    Template files with Jinja2 and transfer to remote hosts.

    This action plugin processes Jinja2 templates with configurable
    syntax and transfers the rendered content to remote hosts. It
    supports custom template delimiters, newline handling, and
    automatic fallback to raw mode when Python is unavailable on
    the remote host.

    The plugin preserves file permissions when requested and supports
    all standard file module parameters including backup, validation,
    and SELinux context handling.

    .. note::
       This plugin transfers files to remote hosts and requires
       a connection. It supports both native and raw execution modes.
    """

    TRANSFERS_FILES = True
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False
    _supports_diff = True

    def _def_args(self) -> Dict[str, Any]:
        """
        Define and parse module arguments using the file argument spec.

        Builds a comprehensive argument specification that includes all
        file module parameters plus template-specific options like
        Jinja2 syntax customization and raw mode forcing.

        :returns Dict[str, Any]: The validated argument dictionary
            containing all parsed and validated module parameters
        :raises AnsibleActionFail: When argument validation fails

        .. note::
           This method removes the 'attributes' parameter from the file
           argument spec as it's not supported by this plugin.
        """
        self._display.vvv("Defining argument spec")
        argument_spec = get_file_arg_spec()
        argument_spec.pop("attributes")
        argument_spec.update(
            {
                "block_end_string": {
                    "type": "str",
                    "default": BLOCK_END_STRING,
                },
                "block_start_string": {
                    "type": "str",
                    "default": BLOCK_START_STRING,
                },
                "comment_end_string": {
                    "type": "str",
                    "default": COMMENT_END_STRING,
                },
                "comment_start_string": {
                    "type": "str",
                    "default": COMMENT_START_STRING,
                },
                "dest": {"type": "path", "required": True},
                "force": {"type": "bool", "default": True},
                "lstrip_blocks": {"type": "bool", "default": False},
                "newline_sequence": {
                    "type": "str",
                    "choices": ["\n", "\r", "\r\n"],
                    "default": "\n",
                },
                "src": {"type": "path", "required": True},
                "trim_blocks": {"type": "bool", "default": True},
                "backup": {"type": "bool", "default": False},
                "validate": {"type": "str"},
                "variable_end_string": {
                    "type": "str",
                    "default": VARIABLE_END_STRING,
                },
                "variable_start_string": {
                    "type": "str",
                    "default": VARIABLE_START_STRING,
                },
                "_force_raw": {"type": "bool", "default": False},
            }
        )

        validation_result, new_module_args = self.validate_argument_spec(
            argument_spec=argument_spec,
        )

        return new_module_args

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point for the template action plugin.

        Processes Jinja2 templates with custom syntax options and
        transfers the rendered content to remote hosts. Automatically
        falls back to raw mode when Python interpreter is unavailable
        on the remote host.

        :param Optional[str] tmp: Temporary directory path (unused in
            modern Ansible)
        :param Optional[Dict[str, Any]] task_vars: Task variables
            dictionary containing template context
        :returns Dict[str, Any]: Standard Ansible result dictionary

        :raises AnsibleActionFail: When template processing fails,
            required parameters are missing, or file operations fail

        .. note::
           This method attempts native execution first via the copy
           module, then falls back to raw POSIX file operations if
           Python is unavailable on the remote host.
        """

        self._display.vvv("Starting template run()")
        task_vars = task_vars or {}

        new_module_args = self._def_args()

        self.result = super(ActionModule, self).run(tmp, task_vars=task_vars)
        self.result.update(
            {
                "invocation": self._task.args.copy(),
                "changed": False,
                "raw": False,
                "msg": "",
            }
        )

        del tmp

        # Required args
        src = new_module_args.get("src")
        dest = new_module_args.get("dest")
        if not src or not dest:
            raise AnsibleActionFail("src and dest are required")

        # Extract options
        newline_sequence = new_module_args.get("newline_sequence")
        trim_blocks = new_module_args.get("trim_blocks")
        lstrip_blocks = new_module_args.get("lstrip_blocks")

        variable_start_string = new_module_args.get("variable_start_string")
        variable_end_string = new_module_args.get("variable_end_string")
        block_start_string = new_module_args.get("block_start_string")
        block_end_string = new_module_args.get("block_end_string")
        comment_start_string = new_module_args.get("comment_start_string")
        comment_end_string = new_module_args.get("comment_end_string")
        force = new_module_args.get("force")

        self.force_raw = new_module_args.get("_force_raw")

        # Resolve src
        try:
            resolved_src = self._find_needle("templates", src)
        except AnsibleError as e:
            raise AnsibleActionFail(to_text(e))

        # Preserve mode if requested
        mode = new_module_args.get("mode")
        if mode == "preserve":
            mode = "0%03o" % stat.S_IMODE(os.stat(resolved_src).st_mode)

        # Template content - use trust_as_template like builtin module
        template_data = trust_as_template(self._loader.get_text_file_contents(resolved_src))

        searchpath = task_vars.get("ansible_search_path", [])
        searchpath.extend(
            [self._loader._basedir, os.path.dirname(resolved_src)]
        )
        searchpath = [
            os.path.join(p, "templates") for p in searchpath
        ] + searchpath

        # add ansible 'template' vars - match builtin module approach
        temp_vars = task_vars.copy()
        temp_vars.update(
            generate_ansible_template_vars(
                path=src,
                fullpath=resolved_src,
                dest_path=dest,
                include_ansible_managed='ansible_managed' not in temp_vars,
            )
        )

        overrides = {
            "block_start_string": block_start_string,
            "block_end_string": block_end_string,
            "variable_start_string": variable_start_string,
            "variable_end_string": variable_end_string,
            "comment_start_string": comment_start_string,
            "comment_end_string": comment_end_string,
            "trim_blocks": trim_blocks,
            "lstrip_blocks": lstrip_blocks,
            "newline_sequence": newline_sequence,
        }

        # Debug: Check temp_vars content
        self._display.warning(f"DEBUG: temp_vars keys: {list(temp_vars.keys())}")
        self._display.warning(f"DEBUG: greeting_var in temp_vars: {temp_vars.get('greeting_var', 'NOT_FOUND')}")

        # Create templar exactly like builtin module
        data_templar = self._templar.copy_with_new_env(
            searchpath=searchpath, available_variables=temp_vars
        )

        # Debug: Check templar available_variables
        self._display.warning(f"DEBUG: templar.available_variables keys: {list(data_templar.available_variables.keys())}")
        self._display.warning(f"DEBUG: greeting_var in templar: {data_templar.available_variables.get('greeting_var', 'NOT_FOUND')}")

        resultant = data_templar.template(
            template_data, escape_backslashes=False, overrides=overrides
        )

        if resultant is None:
            resultant = ''

        result_text = resultant
        # Debug: Check result after templating
        self._display.warning(f"DEBUG: template_data: '{template_data.strip()}'")
        self._display.warning(f"DEBUG: result_text: '{result_text.strip()}'")
        self._display.warning(f"DEBUG: force_raw: {self.force_raw}")

        # Create temp file
        local_tempdir = tempfile.mkdtemp(dir=C.DEFAULT_LOCAL_TMP)
        result_file = os.path.join(
            local_tempdir, os.path.basename(resolved_src)
        )
        with open(to_bytes(result_file), "wb") as f:
            f.write(to_bytes(result_text, encoding="utf-8"))

        try:
            if not self.force_raw:
                self._display.vvv("Attempt native execution to detect Python")
                new_task = self._task.copy()
                new_task.args["src"] = result_file
                new_task.args["dest"] = dest
                new_task.args["follow"] = True
                new_task.args["mode"] = mode

                for remove in (
                    "newline_sequence",
                    "block_start_string",
                    "block_end_string",
                    "variable_start_string",
                    "variable_end_string",
                    "comment_start_string",
                    "comment_end_string",
                    "trim_blocks",
                    "lstrip_blocks",
                    "_force_raw",
                ):
                    new_task.args.pop(remove, None)

                copy_action = self._shared_loader_obj.action_loader.get(
                    "ansible.legacy.copy",
                    task=new_task,
                    connection=self._connection,
                    play_context=self._play_context,
                    loader=self._loader,
                    templar=self._templar,
                    shared_loader_obj=self._shared_loader_obj,
                )
                copy_result = copy_action.run(task_vars=task_vars)

                if not self._is_interpreter_missing(copy_result):
                    self._display.vvv("Delegated to ansible.builtin.copy")
                    copy_result.pop("invocation", None)
                    self.result["raw"] = False
                    self.result.update(copy_result)
                    return self.result
                else:
                    self._display.vvv(
                        "Python missing — falling back to raw mode"
                    )
                    self.force_raw = True

            if self.force_raw:
                try:
                    self._display.vvv(
                        "Creating parent directories (if needed)"
                    )
                    self._mk_dest_dir(dest, task_vars=task_vars)

                    self._display.vvv(f"Writing rendered template to {dest}")
                    perms = {
                        key: new_module_args[key]
                        for key in (
                            "owner",
                            "group",
                            "mode",
                            "selevel",
                            "serole",
                            "setype",
                            "seuser",
                        )
                    }

                    if not force:
                        dest_stat = self._pseudo_stat(
                            dest, task_vars=task_vars
                        )

                    if force or not dest_stat["exists"]:
                        write_result = self._write_file(
                            content=result_text,
                            dest=dest,
                            perms=perms,
                            backup=new_module_args.get("backup"),
                            validate_cmd=new_module_args.get("validate"),
                            check_mode=self._task.check_mode,
                            task_vars=task_vars,
                        )
                        self.result.update(write_result)

                    elif not force:
                        self.result["msg"] = (
                            "File exists and force is disabled, taking no "
                            "action"
                        )

                    else:
                        raise AnsibleActionFail("We should never get here")

                    self.result["raw"] = True

                except Exception as e:
                    self.result.update(
                        {
                            "failed": True,
                            "msg": (
                                f"Template rendering or writing failed: {e}"
                            ),
                        }
                    )
        finally:
            # Clean up temporary files
            shutil.rmtree(
                to_bytes(local_tempdir, errors="surrogate_or_strict")
            )
            self._remove_tmp_path(self._connection._shell.tmpdir)

        return self.result
