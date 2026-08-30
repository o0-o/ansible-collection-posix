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
#   - The template and lineinfile_dedupe action plugins in this
#     collection, themselves adapted from Ansible core's template
#     action plugin and lineinfile module (GPL-3.0-or-later)
#
# This file is part of the o0_o.posix Ansible Collection.

from __future__ import annotations

import os
import stat as stat_module
from typing import Any, Optional

from jinja2.defaults import (
    BLOCK_END_STRING,
    BLOCK_START_STRING,
    COMMENT_END_STRING,
    COMMENT_START_STRING,
    VARIABLE_END_STRING,
    VARIABLE_START_STRING,
)

from ansible import __version__ as ansible_version
from ansible.errors import AnsibleActionFail, AnsibleError
from ansible.module_utils.common.file import get_file_arg_spec
from ansible.module_utils.common.text.converters import to_bytes, to_text
from ansible.plugins.action import ActionBase
from ansible_collections.o0_o.utils.plugins.module_utils import (
    truthy_or_string,
)
from ansible_collections.o0_o.posix.plugins.module_utils import (
    WritePosixActionBase,
    ensure_block,
    ensure_line,
    normalize_mode,
    remove_block,
    remove_lines,
)

# The families a task selects through its canary argument. Exactly one
# canary may be present; a task with none must name a bare file state.
CANARY_ARGS = ("content", "src", "template", "line", "block")

# States that stand alone, without a canary argument
BARE_STATES = ("absent", "directory", "touch", "link")


def _is_ansible_2_19_plus() -> bool:
    """Check if running on Ansible 2.19 or later.

    :returns bool: True if the Ansible version is 2.19 or higher
    """
    try:
        version_parts = ansible_version.split(".")
        major = int(version_parts[0])
        minor = int(version_parts[1]) if len(version_parts) > 1 else 0
        return (major > 2) or (major == 2 and minor >= 19)
    except (ValueError, IndexError):
        return False


IS_ANSIBLE_2_19_PLUS = _is_ansible_2_19_plus()

if IS_ANSIBLE_2_19_PLUS:
    from ansible.template import trust_as_template
    from ansible._internal._templating import _template_vars

    generate_ansible_template_vars = None
    AnsibleEnvironment = None
else:
    from ansible.template import (
        generate_ansible_template_vars,
        AnsibleEnvironment,
    )

    trust_as_template = None
    _template_vars = None


class ActionModule(WritePosixActionBase, ActionBase):
    """Write files on POSIX hosts, generalized over source and edit.

    One module funnels every file mutation: literal content, copied
    files (controller or remote source), rendered templates, line
    edits with deduplication, marked block edits, and bare file state
    (directory, touch, link, absent). The argument present in the
    task selects the family, so a playbook reads as a verb and a
    source.

    All families support raw fallback for hosts without Python, check
    mode, and diff, and the content families share backup, validate,
    and permission handling through the write machinery.

    Check mode withholds placement and nothing else. Probing the
    destination and staging the candidate happen for real, so the
    change reported is read off the file that would have landed and a
    validate command vets that file rather than being skipped.
    """

    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False
    _supports_diff = True

    def _def_args(self) -> dict[str, Any]:
        """Define and validate the union argument spec.

        :returns dict[str, Any]: The validated argument dictionary
        :raises AnsibleActionFail: When validation fails
        """
        argument_spec = get_file_arg_spec()
        argument_spec.pop("attributes")
        argument_spec.update(
            {
                "dest": {
                    "type": "path",
                    "required": True,
                    "aliases": ["path", "name"],
                },
                "state": {
                    "type": "str",
                    "choices": [
                        "present",
                        "absent",
                        "directory",
                        "touch",
                        "link",
                    ],
                    "default": "present",
                },
                # Family canaries: exactly one selects the operation
                "content": {"type": "str", "no_log": False},
                "src": {"type": "path"},
                "template": {"type": "path"},
                "line": {"type": "str", "aliases": ["value"]},
                "block": {"type": "str"},
                # Copy family
                "remote_src": {"type": "bool", "default": False},
                "force": {"type": "bool", "default": True},
                # Template family
                "block_start_string": {
                    "type": "str",
                    "default": BLOCK_START_STRING,
                },
                "block_end_string": {
                    "type": "str",
                    "default": BLOCK_END_STRING,
                },
                "variable_start_string": {
                    "type": "str",
                    "default": VARIABLE_START_STRING,
                },
                "variable_end_string": {
                    "type": "str",
                    "default": VARIABLE_END_STRING,
                },
                "comment_start_string": {
                    "type": "str",
                    "default": COMMENT_START_STRING,
                },
                "comment_end_string": {
                    "type": "str",
                    "default": COMMENT_END_STRING,
                },
                "trim_blocks": {"type": "bool", "default": True},
                "lstrip_blocks": {"type": "bool", "default": False},
                "newline_sequence": {
                    "type": "str",
                    "choices": ["\n", "\r", "\r\n"],
                    "default": "\n",
                },
                # Line family
                "regexp": {"type": "str", "aliases": ["regex"]},
                "search_string": {"type": "str"},
                "insertafter": {"type": "str"},
                "insertbefore": {"type": "str"},
                "firstmatch": {"type": "bool", "default": False},
                "backrefs": {"type": "bool", "default": False},
                "dedupe": {"type": "bool", "default": True},
                # Block family
                "marker": {
                    "type": "str",
                    "default": "# {mark} ANSIBLE MANAGED BLOCK",
                },
                "marker_begin": {"type": "str", "default": "BEGIN"},
                "marker_end": {"type": "str", "default": "END"},
                # Line and block families
                "create": {"type": "bool", "default": False},
                # Link family
                "target": {"type": "path"},
                # Shared
                "backup": {"type": "bool", "default": False},
                "validate": {"type": "str"},
                "raw": {"type": "raw", "default": "auto"},
            }
        )

        mutually_exclusive = [
            list(CANARY_ARGS),
            ["insertbefore", "insertafter"],
            ["regexp", "search_string"],
            ["backrefs", "search_string"],
        ]
        required_if = [
            ("state", "link", ("target",)),
        ]

        validation_result, new_module_args = self.validate_argument_spec(
            argument_spec=argument_spec,
            mutually_exclusive=mutually_exclusive,
            required_if=required_if,
        )

        # A mode is raw, so an unquoted one arrives as an integer.
        # Settle it into the octal string every command downstream
        # takes here, at the one boundary it enters through, so
        # nothing further in asks what shape it is.
        try:
            new_module_args["mode"] = normalize_mode(
                new_module_args.get("mode")
            )
        except ValueError as e:
            raise AnsibleActionFail(str(e)) from e

        return new_module_args

    def _resolve_family(self, args: dict[str, Any]) -> str:
        """Resolve the operation family from the canary arguments.

        :param dict[str, Any] args: Validated module arguments
        :returns str: One of 'content', 'src', 'template', 'line',
            'block', or 'state'
        :raises AnsibleActionFail: When no family applies
        """
        canaries = [name for name in CANARY_ARGS if args.get(name) is not None]

        state = args["state"]

        if len(canaries) == 1:
            family = canaries[0]
            if family in ("content", "src", "template"):
                if state != "present":
                    raise AnsibleActionFail(
                        f"{family} requires state=present, got state={state}"
                    )
            elif state not in ("present", "absent"):
                raise AnsibleActionFail(
                    f"{family} requires state=present or state=absent, "
                    f"got state={state}"
                )
            return family

        if state in BARE_STATES:
            return "state"

        raise AnsibleActionFail(
            "one of content, src, template, line, or block is required "
            "with state=present; a bare task requires state to be one "
            f"of {', '.join(BARE_STATES)}"
        )

    def _audit_line_args(self, args: dict[str, Any]) -> None:
        """Enforce the line family's argument dependencies.

        :param dict[str, Any] args: Validated module arguments
        :raises AnsibleActionFail: On a dependency violation
        """
        if "" in (args.get("regexp"), args.get("search_string")):
            param_name = "search string"
            msg = (
                "The %s is an empty string, which will match every line "
                "in the file. This may have unintended consequences, "
                "such as replacing the last line in the file rather "
                "than appending."
            )
            if args.get("regexp") == "":
                param_name = "regular expression"
                msg += (
                    " If this is desired, use '^' to match every line "
                    "in the file and avoid this warning."
                )
            self._display.warning(
                f"[{self.inventory_hostname}] " + (msg % param_name)
            )

        if args["state"] == "present":
            if args["backrefs"] and not args.get("regexp"):
                raise AnsibleActionFail(
                    "regexp is required with backrefs=true"
                )

    def _read_dest_lines(
        self,
        dest: str,
        create: bool,
        task_vars: dict[str, Any],
        missing_ok: bool = False,
    ) -> Optional[list[str]]:
        """Read the destination's lines for an edit family.

        :param str dest: Destination path on the remote host
        :param bool create: Whether a missing destination is allowed
        :param dict[str, Any] task_vars: Task variables
        :param bool missing_ok: Return None for a missing destination
            instead of failing; removals treat that as nothing to do
        :returns Optional[list[str]]: Current lines, empty when absent
            and create is set, None when absent and missing_ok is set
        :raises AnsibleActionFail: When the destination is missing
            without create or missing_ok, is not a file, or cannot be
            read
        """
        dest_stat = self._pseudo_stat(dest, task_vars=task_vars)
        self.result["raw"] = dest_stat.get("raw", False)

        if not dest_stat["exists"]:
            if create:
                return []
            if missing_ok:
                return None
            raise AnsibleActionFail(f"Destination {dest} does not exist!")

        if dest_stat["type"] != "file":
            raise AnsibleActionFail(f"Path {dest} is a {dest_stat['type']}!")

        read_result = self._read(
            paths=dest,
            content=True,
            lines=True,
            task_vars=task_vars,
            check_mode=False,
        )
        if read_result.get("failed"):
            raise AnsibleActionFail(
                f"Could not read contents of file '{dest}': "
                f"{read_result.get('msg', '')}"
            )
        path_data = read_result.get("paths", {}).get(dest, {})
        lines = path_data.get("lines")
        if lines is None:
            lines = path_data.get("content", "").splitlines()
        return lines

    def _resolve_controller_src(self, src: str) -> str:
        """Resolve a controller-side source path through the needles.

        :param str src: The source path from the task
        :returns str: The resolved absolute path
        :raises AnsibleActionFail: When the source cannot be found
        """
        try:
            return self._find_needle("files", src)
        except AnsibleError as e:
            raise AnsibleActionFail(to_text(e))

    def _read_controller_file(self, path: str) -> str:
        """Read a controller-side file as text.

        :param str path: Absolute path on the controller
        :returns str: The file's text content
        :raises AnsibleActionFail: On binary or undecodable content
        """
        b_path = to_bytes(path, errors="surrogate_or_strict")
        with open(b_path, "rb") as f:
            data = f.read()
        try:
            return to_text(data, errors="surrogate_or_strict")
        except UnicodeError:
            raise AnsibleActionFail(
                f"Source file {path} is not valid UTF-8 text; binary "
                "sources are not supported"
            )

    def _handle_content(
        self,
        args: dict[str, Any],
        task_vars: dict[str, Any],
    ) -> str:
        """Return the literal content family's content.

        :param dict[str, Any] args: Validated module arguments
        :param dict[str, Any] task_vars: Task variables
        :returns str: The content to write
        """
        return args["content"]

    def _handle_src(
        self,
        args: dict[str, Any],
        task_vars: dict[str, Any],
    ) -> str:
        """Return the copy family's content.

        :param dict[str, Any] args: Validated module arguments
        :param dict[str, Any] task_vars: Task variables
        :returns str: The content to write
        :raises AnsibleActionFail: On unreadable or binary sources
        """
        src = args["src"]

        if args["remote_src"]:
            if args.get("mode") == "preserve":
                raise AnsibleActionFail(
                    "mode=preserve is not supported with remote_src"
                )
            read_result = self._read(
                paths=src,
                content=True,
                task_vars=task_vars,
                check_mode=False,
            )
            if read_result.get("failed"):
                raise AnsibleActionFail(
                    f"Could not read remote source '{src}': "
                    f"{read_result.get('msg', '')}"
                )
            path_data = read_result.get("paths", {}).get(src, {})
            if "content" not in path_data:
                raise AnsibleActionFail(
                    f"Remote source '{src}' has no readable content"
                )
            if path_data.get("encoding") in ("base64", "hex"):
                raise AnsibleActionFail(
                    f"Remote source '{src}' is binary; binary sources "
                    "are not supported"
                )
            return path_data["content"]

        resolved_src = self._resolve_controller_src(src)

        if args.get("mode") == "preserve":
            args["mode"] = "0%03o" % stat_module.S_IMODE(
                os.stat(resolved_src).st_mode
            )

        return self._read_controller_file(resolved_src)

    def _handle_template(
        self,
        args: dict[str, Any],
        task_vars: dict[str, Any],
    ) -> str:
        """Render the template family's content on the controller.

        :param dict[str, Any] args: Validated module arguments
        :param dict[str, Any] task_vars: Task variables
        :returns str: The rendered content
        :raises AnsibleActionFail: On resolution or rendering failure
        """
        src = args["template"]
        dest = args["dest"]

        try:
            resolved_src = self._find_needle("templates", src)
        except AnsibleError as e:
            raise AnsibleActionFail(to_text(e))

        if args.get("mode") == "preserve":
            args["mode"] = "0%03o" % stat_module.S_IMODE(
                os.stat(resolved_src).st_mode
            )

        # Load the template source, version-specific
        if IS_ANSIBLE_2_19_PLUS:
            template_data = trust_as_template(
                self._loader.get_text_file_contents(resolved_src)
            )
        else:
            try:
                tmp_source = self._loader.get_real_file(resolved_src)
            except Exception:
                tmp_source = resolved_src

            b_tmp_source = to_bytes(tmp_source, errors="surrogate_or_strict")
            try:
                with open(b_tmp_source, "rb") as f:
                    try:
                        template_data = to_text(
                            f.read(), errors="surrogate_or_strict"
                        )
                    except UnicodeError:
                        raise AnsibleActionFail(
                            "Template source files must be utf-8 encoded"
                        )
            finally:
                if tmp_source != resolved_src:
                    try:
                        self._loader.cleanup_tmp_file(b_tmp_source)
                    except Exception:
                        pass  # Ignore cleanup errors

        searchpath = task_vars.get("ansible_search_path", [])
        searchpath.extend(
            [self._loader._basedir, os.path.dirname(resolved_src)]
        )
        searchpath = [
            os.path.join(p, "templates") for p in searchpath
        ] + searchpath

        overrides = {
            "block_start_string": args["block_start_string"],
            "block_end_string": args["block_end_string"],
            "variable_start_string": args["variable_start_string"],
            "variable_end_string": args["variable_end_string"],
            "comment_start_string": args["comment_start_string"],
            "comment_end_string": args["comment_end_string"],
            "trim_blocks": args["trim_blocks"],
            "lstrip_blocks": args["lstrip_blocks"],
            "newline_sequence": args["newline_sequence"],
        }

        temp_vars = task_vars.copy()

        if IS_ANSIBLE_2_19_PLUS:
            temp_vars.update(
                _template_vars.generate_ansible_template_vars(
                    path=src,
                    fullpath=resolved_src,
                    dest_path=dest,
                    include_ansible_managed=(
                        "ansible_managed" not in temp_vars
                    ),
                )
            )
            data_templar = self._templar.copy_with_new_env(
                searchpath=searchpath, available_variables=temp_vars
            )
            resultant = data_templar.template(
                template_data,
                escape_backslashes=False,
                overrides=overrides,
            )
        else:
            temp_vars.update(
                generate_ansible_template_vars(src, resolved_src, dest)
            )
            templar = self._templar.copy_with_new_env(
                environment_class=AnsibleEnvironment,
                searchpath=searchpath,
                newline_sequence=args["newline_sequence"],
                available_variables=temp_vars,
            )
            resultant = templar.do_template(
                template_data,
                preserve_trailing_newlines=True,
                escape_backslashes=False,
                overrides=overrides,
            )

        return resultant if resultant is not None else ""

    def _handle_line(
        self,
        args: dict[str, Any],
        task_vars: dict[str, Any],
    ) -> Optional[tuple[list[str], str]]:
        """Compute the line family's new lines.

        :param dict[str, Any] args: Validated module arguments
        :param dict[str, Any] task_vars: Task variables
        :returns Optional[tuple[list[str], str]]: (new_lines, msg), or
            None when removing from a file that does not exist
        :raises AnsibleActionFail: On invalid arguments or state
        """
        self._audit_line_args(args)

        removing = args["state"] == "absent"
        lines = self._read_dest_lines(
            args["dest"],
            args["create"] and not removing,
            task_vars,
            missing_ok=removing,
        )
        if lines is None:
            self.result["msg"] = "file not present, nothing to do"
            return None

        try:
            if not removing:
                return ensure_line(
                    lines,
                    args["line"],
                    regexp=args.get("regexp"),
                    search_string=args.get("search_string"),
                    insertafter=args.get("insertafter"),
                    insertbefore=args.get("insertbefore"),
                    firstmatch=args["firstmatch"],
                    backrefs=args["backrefs"],
                    dedupe=args["dedupe"],
                )
            new_lines, removed = remove_lines(
                lines,
                line=args.get("line"),
                regexp=args.get("regexp"),
                search_string=args.get("search_string"),
            )
            self.result["found"] = removed
            msg = (
                f"{removed} line(s) removed" if removed else "no changes made"
            )
            return new_lines, msg
        except ValueError as e:
            raise AnsibleActionFail(str(e)) from e

    def _handle_block(
        self,
        args: dict[str, Any],
        task_vars: dict[str, Any],
    ) -> Optional[tuple[list[str], str]]:
        """Compute the block family's new lines.

        :param dict[str, Any] args: Validated module arguments
        :param dict[str, Any] task_vars: Task variables
        :returns Optional[tuple[list[str], str]]: (new_lines, msg), or
            None when removing from a file that does not exist
        :raises AnsibleActionFail: On invalid arguments or state
        """
        removing = args["state"] == "absent"
        lines = self._read_dest_lines(
            args["dest"],
            args["create"] and not removing,
            task_vars,
            missing_ok=removing,
        )
        if lines is None:
            self.result["msg"] = "file not present, nothing to do"
            return None

        try:
            if not removing:
                return ensure_block(
                    lines,
                    args["block"],
                    marker=args["marker"],
                    marker_begin=args["marker_begin"],
                    marker_end=args["marker_end"],
                    insertafter=args.get("insertafter"),
                    insertbefore=args.get("insertbefore"),
                )
            return remove_block(
                lines,
                marker=args["marker"],
                marker_begin=args["marker_begin"],
                marker_end=args["marker_end"],
            )
        except ValueError as e:
            raise AnsibleActionFail(str(e)) from e

    def _perms_from_args(self, args: dict[str, Any]) -> dict[str, Any]:
        """Collect the permission arguments into one dictionary.

        :param dict[str, Any] args: Validated module arguments
        :returns dict[str, Any]: Keys owner, group, mode, and the
            SELinux quartet
        """
        return {
            key: args.get(key)
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

    def _record_diff(
        self,
        dest: str,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> None:
        """Record a bare state's before and after for diff mode.

        The content families diff their text through the write
        machinery. A bare state has no text to diff, so its diff names
        the attributes of the path the task moves, and a state change
        carrying permissions merges both into the one report.

        :param str dest: The path the diff describes
        :param dict[str, Any] before: Attributes as they were found
        :param dict[str, Any] after: Attributes as the task leaves them
        """
        if not self._task.diff:
            return

        diff = self.result.setdefault(
            "diff",
            {
                "before_header": dest,
                "after_header": dest,
                "before": {},
                "after": {},
            },
        )
        diff["before"].update(before)
        diff["after"].update(after)

    def _write_content(
        self,
        content: Any,
        args: dict[str, Any],
        task_vars: dict[str, Any],
    ) -> None:
        """Write content through the shared write machinery.

        :param content: A string or list of lines to write
        :param dict[str, Any] args: Validated module arguments
        :param dict[str, Any] task_vars: Task variables
        :raises AnsibleActionFail: When the write fails
        """
        dest = args["dest"]

        self._mk_dest_dir(dest, task_vars=task_vars)
        if self.result.get("failed"):
            return

        try:
            write_result = self._write_file(
                content=content,
                dest=dest,
                perms=self._perms_from_args(args),
                backup=args["backup"],
                validate_cmd=args.get("validate"),
                check_mode=self._task.check_mode,
                task_vars=task_vars,
            )
        except Exception as e:
            raise AnsibleActionFail(
                f"Failed to write file: {to_text(e)}"
            ) from e

        edit_msg = self.result.get("msg", "")
        self.result.update(write_result)
        if edit_msg and write_result.get("changed"):
            self.result["msg"] = edit_msg

    def _handle_state(
        self,
        args: dict[str, Any],
        task_vars: dict[str, Any],
    ) -> None:
        """Apply a bare file state to the destination.

        :param dict[str, Any] args: Validated module arguments
        :param dict[str, Any] task_vars: Task variables
        :raises AnsibleActionFail: When the operation fails
        """
        dest = args["dest"]
        state = args["state"]
        check_mode = self._task.check_mode
        dest_stat = self._pseudo_stat(dest, task_vars=task_vars)
        self.result["raw"] = dest_stat.get("raw", False)

        if state == "absent":
            if not dest_stat["exists"]:
                self.result["msg"] = "path already absent"
                return
            self.result["changed"] = True
            self._record_diff(
                dest,
                {"state": dest_stat["type"]},
                {"state": "absent"},
            )
            if check_mode:
                self.result["msg"] = (
                    "Check mode: path would have been removed."
                )
                return
            rm_args = ["rm", "-f"]
            if dest_stat["type"] == "directory":
                rm_args = ["rm", "-rf"]
            rm_result = self._command(rm_args + [dest], task_vars=task_vars)
            if rm_result["rc"] != 0:
                raise AnsibleActionFail(
                    f"Failed to remove {dest}: {rm_result.get('stderr', '')}"
                )
            self.result["msg"] = "path removed"
            return

        if state == "directory":
            if not dest_stat["exists"]:
                self.result["changed"] = True
                self._record_diff(
                    dest,
                    {"state": "absent"},
                    {"state": "directory"},
                )
                if check_mode:
                    self.result["msg"] = (
                        "Check mode: directory would have been created."
                    )
                    return
                self._mkdir(dest, task_vars=task_vars, parents=True)
            elif dest_stat["type"] != "directory":
                raise AnsibleActionFail(
                    f"Path {dest} exists and is a "
                    f"{dest_stat['type']}, not a directory"
                )
            self._apply_state_perms(args, task_vars, check_mode)
            if not self.result.get("msg"):
                self.result["msg"] = (
                    "directory present"
                    if not self.result["changed"]
                    else "directory created"
                )
            return

        if state == "touch":
            if not dest_stat["exists"]:
                self.result["changed"] = True
                self._record_diff(
                    dest,
                    {"state": "absent"},
                    {"state": "file"},
                )
                if check_mode:
                    self.result["msg"] = (
                        "Check mode: file would have been created."
                    )
                    return
                touch_result = self._command(
                    ["touch", dest], task_vars=task_vars
                )
                if touch_result["rc"] != 0:
                    raise AnsibleActionFail(
                        f"Failed to touch {dest}: "
                        f"{touch_result.get('stderr', '')}"
                    )
            self._apply_state_perms(args, task_vars, check_mode)
            if not self.result.get("msg"):
                self.result["msg"] = (
                    "file present"
                    if not self.result["changed"]
                    else "file created"
                )
            return

        if state == "link":
            target = args["target"]
            # test -e follows symlinks, so a dangling link reports
            # exists=False in dest_stat; probe the link itself so a
            # link already pointing at the requested (possibly absent)
            # target stays idempotent
            symlink_test = self._command(
                ["test", "-L", dest],
                task_vars=task_vars,
                check_mode=False,
            )
            before = {"state": "absent"}
            if symlink_test["rc"] == 0:
                readlink_result = self._command(
                    ["readlink", dest],
                    task_vars=task_vars,
                    check_mode=False,
                )
                before = {"state": "link"}
                if readlink_result["rc"] == 0:
                    old_target = readlink_result["stdout"].strip()
                    if old_target == target:
                        self.result["msg"] = "link already points at target"
                        return
                    before["target"] = old_target
                    # Repointing an existing link is the one mutation
                    # this branch performs on prior state; force gates
                    # it exactly as it gates content overwrites
                    if not args["force"]:
                        raise AnsibleActionFail(
                            f"Path {dest} is a link to {old_target}; "
                            f"refusing to repoint it with force disabled"
                        )
            elif dest_stat["exists"]:
                raise AnsibleActionFail(
                    f"Path {dest} exists and is a "
                    f"{dest_stat['type']}, not a symlink"
                )
            self.result["changed"] = True
            self._record_diff(
                dest, before, {"state": "link", "target": target}
            )
            if check_mode:
                self.result["msg"] = (
                    "Check mode: link would have been created."
                )
                return
            ln_result = self._command(
                ["ln", "-sfn", target, dest], task_vars=task_vars
            )
            if ln_result["rc"] != 0:
                raise AnsibleActionFail(
                    f"Failed to link {dest} to {target}: "
                    f"{ln_result.get('stderr', '')}"
                )
            self.result["msg"] = "link created"
            return

        raise AnsibleActionFail(f"Unhandled state: {state}")

    def _apply_state_perms(
        self,
        args: dict[str, Any],
        task_vars: dict[str, Any],
        check_mode: bool,
    ) -> None:
        """Apply requested permissions for a bare-state operation.

        Compares against the current permissions first so an untouched
        path reports unchanged, then applies through the shared
        machinery outside check mode.

        :param dict[str, Any] args: Validated module arguments
        :param dict[str, Any] task_vars: Task variables
        :param bool check_mode: Whether check mode is active
        :raises AnsibleActionFail: When applying fails
        """
        perms = {k: v for k, v in self._perms_from_args(args).items() if v}
        if not perms:
            return

        dest = args["dest"]
        selinux = self._check_selinux_tools(perms, task_vars=task_vars)

        try:
            old_perms = self._get_perms(
                dest, selinux=selinux, task_vars=task_vars
            )
        except RuntimeError:
            old_perms = {}

        perms_changed = False
        before: dict[str, Any] = {}
        after: dict[str, Any] = {}
        for key in ("owner", "group", "seuser", "serole", "setype", "selevel"):
            if perms.get(key) and perms[key] != old_perms.get(key):
                perms_changed = True
                before[key] = old_perms.get(key)
                after[key] = perms[key]
        if perms.get("mode") is not None:
            try:
                symbolic = self._convert_octal_mode_to_symbolic(perms["mode"])
                if symbolic != old_perms.get("mode"):
                    perms_changed = True
                    before["mode"] = old_perms.get("mode")
                    after["mode"] = symbolic
            except (RuntimeError, ValueError) as e:
                raise AnsibleActionFail(f"Invalid mode: {perms['mode']}: {e}")

        if not perms_changed:
            return

        self.result["changed"] = True
        self._record_diff(dest, before, after)
        if check_mode:
            self.result["msg"] = (
                "Check mode: permissions would have been changed."
            )
            return

        try:
            self._apply_perms_and_selinux(
                dest, perms, selinux, task_vars=task_vars
            )
        except RuntimeError as e:
            raise AnsibleActionFail(str(e)) from e

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute the write operation the task's arguments select.

        :param Optional[str] tmp: Unused temporary directory path
        :param Optional[dict[str, Any]] task_vars: Available Ansible
            variables
        :returns dict[str, Any]: Result dictionary with changed, msg,
            raw, and family-specific keys
        """
        task_vars = task_vars or {}
        self._def_inventory_hostname(task_vars)

        self.result = super().run(tmp, task_vars=task_vars)
        del tmp  # unused
        self.result.update(
            {
                "invocation": self._task.args.copy(),
                "changed": False,
                "raw": False,
                "msg": "",
            }
        )

        new_module_args = self._def_args()

        try:
            self.raw = truthy_or_string(new_module_args.get("raw"), ["auto"])
        except ValueError as e:
            raise AnsibleActionFail(str(e)) from e

        family = self._resolve_family(new_module_args)
        self._display.vvv(f"write: resolved family '{family}'")

        try:
            if family in ("content", "src", "template"):
                # force applies to whole-content writes only: an edit
                # family exists to modify files that already exist
                if not new_module_args["force"]:
                    dest_stat = self._pseudo_stat(
                        new_module_args["dest"], task_vars=task_vars
                    )
                    if dest_stat["exists"]:
                        self.result["msg"] = (
                            "File exists and force is disabled, "
                            "taking no action"
                        )
                        self.result["raw"] = dest_stat.get("raw", False)
                        return self.result

            if family == "content":
                content = self._handle_content(new_module_args, task_vars)
                self._write_content(content, new_module_args, task_vars)
            elif family == "src":
                content = self._handle_src(new_module_args, task_vars)
                self._write_content(content, new_module_args, task_vars)
            elif family == "template":
                content = self._handle_template(new_module_args, task_vars)
                self._write_content(content, new_module_args, task_vars)
            elif family == "line":
                edit = self._handle_line(new_module_args, task_vars)
                if edit is not None:
                    new_lines, msg = edit
                    self.result["msg"] = msg
                    self._write_content(new_lines, new_module_args, task_vars)
            elif family == "block":
                edit = self._handle_block(new_module_args, task_vars)
                if edit is not None:
                    new_lines, msg = edit
                    self.result["msg"] = msg
                    self._write_content(new_lines, new_module_args, task_vars)
            else:
                self._handle_state(new_module_args, task_vars)
        finally:
            # Report the raw mode the machinery settled on
            self.result["raw"] = self.raw is True
            self._remove_tmp_path(self._connection._shell.tmpdir)

        return self.result
