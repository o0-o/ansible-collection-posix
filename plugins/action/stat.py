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

import re
from numbers import Number

from typing import Any, Dict, Optional

from ansible.errors import AnsibleActionFail
from ansible.module_utils.common.text.converters import to_text
from ansible.plugins.action import ActionBase

from ansible_collections.o0_o.posix.plugins.module_utils import (
    device_from_hex_major_minor,
    device_from_major_minor,
    device_value,
    jc_parse,
    PosixActionBase,
)


class ActionModule(PosixActionBase, ActionBase):
    """Gather file metadata using stat with jc fallback.

    This action plugin provides file metadata gathering that
    automatically falls back to parsing stat command output with jc
    when Python is not available on the remote host.

    Raw mode limitations (when _force_raw=true or Python unavailable):
    - Timestamps have second precision only (not millisecond)
    - The 'version' field is not available (requires ioctl/statx)
    - The 'generation' field is not available on Linux
      (requires ioctl, BSD/macOS may support via stat -f %v)
    """

    TRANSFERS_FILES = False
    _requires_connection = True
    _supports_check_mode = True
    _supports_async = False

    def _device_type_value(
        self,
        jc_data: Dict[str, Any],
        task_vars: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Get device type (rdev) with intelligent fallback detection.

        Determines the device type value based on file type and
        available data. For regular files and similar types, returns 0.
        For device files, attempts to fetch the actual rdev if not
        already present in jc output.

        :param Dict[str, Any] jc_data: Parsed jc stat output
        :param Optional[Dict[str, Any]] task_vars: Available Ansible
            variables
        :returns int: Device type number (rdev), 0 for non-device files
        """
        # If jc already parsed rdev, use it
        rdev = jc_data.get("rdev")
        if rdev is not None:
            # Convert if needed (decimal major,minor format)
            if isinstance(rdev, str) and "," in rdev:
                rdev_int = device_from_major_minor(rdev)
                if rdev_int is not None:
                    return rdev_int
            # Direct integer or convertible string
            try:
                return int(rdev) if rdev else 0
            except (ValueError, TypeError):
                pass

        # Determine file type from flags to decide if we need rdev
        flags = jc_data.get("flags", "")
        if not flags:
            return 0

        file_type_char = flags[0]

        # File types that always have rdev=0
        # - regular file, d directory, l symlink, p fifo, s socket
        if file_type_char in ("-", "d", "l", "p", "s"):
            return 0

        # Block or character device - need to get rdev value
        if file_type_char in ("b", "c"):
            path = jc_data.get("file")
            if not path:
                return 0

            # Try to get device numbers using stat -c format
            # %t = major in hex, %T = minor in hex
            result = self._cmd(
                ["stat", "-c", "%t,%T", path],
                task_vars=task_vars,
                check_mode=False,
            )

            if result.get("rc") == 0:
                output = result.get("stdout", "").strip()
                if output:
                    rdev_int = device_from_hex_major_minor(output)
                    if rdev_int is not None:
                        return rdev_int

        # Default fallback
        return 0

    def _get_symlink_target(
        self, path: str, task_vars: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Get the immediate target of a symlink using readlink.

        Returns the raw target string as stored in the symlink, which
        may be relative or absolute.

        :param str path: Path to the symlink
        :param Optional[Dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Optional[str]: Target path or None if unavailable
        """
        result = self._cmd(
            ["readlink", path], task_vars=task_vars, check_mode=False
        )

        if result.get("rc") == 0:
            output = result.get("stdout", "").strip()
            if output:
                return output

        return None

    def _get_symlink_source(
        self, path: str, task_vars: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Get the fully resolved target of a symlink.

        Follows all intermediate symlinks to find the ultimate target.
        Uses readlink -f which is available on both GNU and BSD systems.

        :param str path: Path to the symlink
        :param Optional[Dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Optional[str]: Resolved target path or None
        """
        result = self._cmd(
            ["readlink", "-f", path], task_vars=task_vars, check_mode=False
        )

        if result.get("rc") == 0:
            output = result.get("stdout", "").strip()
            if output:
                return output

        return None

    def _stat_with_jc(
        self,
        module_args: Optional[Dict[str, Any]] = None,
        task_vars: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Gather file metadata using stat command and jc parser.

        :param Optional[Dict[str, Any]] module_args: Module arguments
            dictionary containing command parameters
        :param Optional[Dict[str, Any]] task_vars: Task variables
            dictionary
        :returns Dict[str, Any]: Result dictionary with stat
            information
        :raises AnsibleActionFail: When we encounter an unexpected
            result
        """
        path = module_args["path"]
        follow = module_args["follow"]
        get_checksum = module_args["get_checksum"]
        get_mime = module_args["get_mime"]
        get_attributes = module_args["get_attributes"]
        checksum_algorithm = module_args["checksum_algorithm"]
        stat_result = {"exists": False}

        # Run stat command WITHOUT -L first to detect symlinks
        # (we'll handle follow behavior for symlinks separately)
        stat_args = ["stat", path]

        cmd_result = self._cmd(
            stat_args, task_vars=task_vars, check_mode=False
        )

        if cmd_result.get("rc") == 0:
            stat_result = {
                "exists": True,
                # Platform-specific fields - set defaults for
                # compatibility with builtin.stat
                "attr_flags": "",
                "attributes": [],
            }
        else:
            # File doesn't exist or other error
            return stat_result
        self._display.vvv(cmd_result.get("stdout"))

        # Parse with jc
        try:
            parsed = jc_parse("stat", cmd_result.get("stdout", ""))
        except Exception as e:
            raise AnsibleActionFail(
                f"Failed to parse stat output for {path}: {e}"
            )

        # jc audit
        if (
            not parsed
            or not isinstance(parsed, list)
            or len(parsed) == 0
            or not isinstance(parsed[0], dict)
        ):
            raise AnsibleActionFail("jc stat parser returned empty result")
        jc_data = parsed[0]
        self._display.vvv(to_text(jc_data))

        for field in ["file", "flags", "user", "group"]:
            if jc_data.get(field) is None or not isinstance(
                jc_data.get(field), str
            ):
                raise AnsibleActionFail(
                    f"jc stat result missing {field} field (string)"
                )

        for field in [
            "size",
            "links",
            "inode",
            "blocks",
            "access_time_epoch",
            "modify_time_epoch",
            "change_time_epoch",
        ]:
            value = jc_data.get(field)
            if value is None or not isinstance(value, Number):
                raise AnsibleActionFail(
                    f"jc stat result missing {field} field (number): "
                    f"{to_text(value)}"
                )

        # birth_time_epoch is optional - not all systems support it
        birth_time = jc_data.get("birth_time_epoch")
        if birth_time is not None and not isinstance(birth_time, Number):
            raise AnsibleActionFail(
                f"jc stat result has invalid birth_time_epoch: "
                f"{to_text(birth_time)}"
            )

        # 1:1s - use file from jc output, fallback to input path if
        # empty
        result_path = jc_data.get("file")
        if not result_path or not result_path.strip():
            # jc parsing error - use the input path instead
            result_path = path
        stat_result["path"] = result_path
        stat_result["size"] = jc_data["size"]
        stat_result["nlink"] = jc_data.get("links")
        stat_result["inode"] = jc_data.get("inode")
        stat_result["dev"] = device_value(jc_data)
        stat_result["device_type"] = self._device_type_value(
            jc_data, task_vars
        )

        # BSD stat uses different field names than Linux
        # BSD: block_size is filesystem block size, blocks is allocated
        # Linux: io_blocks is filesystem block size, blocks is allocated
        is_bsd = "unix_device" in jc_data
        if is_bsd:
            # Workaround for jc parser bug on OpenBSD: All fields after
            # the timestamps are shifted. The jc parser misaligns:
            #   birth_time <- block_size (as string)
            #   block_size <- blocks
            #   blocks <- unix_flags (usually 0)
            #   unix_flags <- path
            blocks_value = jc_data.get("blocks", 0)
            block_size_value = jc_data.get("block_size", 512)

            if birth_time is None:
                birth_time_str = jc_data.get("birth_time")
                if birth_time_str and isinstance(birth_time_str, str):
                    try:
                        # birth_time field contains the actual
                        # block_size
                        parsed_block_size = int(birth_time_str)
                        if parsed_block_size > 0:
                            # block_size field contains the actual
                            # blocks
                            blocks_value = block_size_value
                            block_size_value = parsed_block_size
                    except (ValueError, TypeError):
                        pass

            stat_result["blocks"] = blocks_value
            stat_result["block_size"] = block_size_value
        else:
            # Linux: blocks and io_blocks fields
            stat_result["blocks"] = jc_data.get("blocks", 0)
            block_size = jc_data.get("io_blocks") or jc_data.get("block_size")
            if block_size:
                stat_result["block_size"] = block_size
            else:
                raise AnsibleActionFail(
                    "jc stat result missing block_size or io_blocks"
                )

        # Convert to float for consistency with builtin.stat
        stat_result["atime"] = float(jc_data["access_time_epoch"])
        stat_result["mtime"] = float(jc_data["modify_time_epoch"])
        stat_result["ctime"] = float(jc_data["change_time_epoch"])

        # Only set birthtime if actually supported (BSD/macOS, not
        # Linux ext4). On Linux ext4, birth_time_epoch might be 0 or
        # equal to ctime. On OpenBSD, it may be None.
        if birth_time and birth_time > 0:
            # On BSD/macOS, always trust birth_time_epoch.
            # On Linux, only if different from ctime.
            if is_bsd or birth_time != jc_data["change_time_epoch"]:
                stat_result["birthtime"] = float(birth_time)

        # File type flags - check if symlink first
        flags = jc_data["flags"]
        flags_re = re.compile(r"^[\-dlcbsp][-rwxSsTt]{9}$")
        if not flags_re.match(flags):
            raise AnsibleActionFail(f"jc flags result invalid: {flags}")

        is_symlink = flags.startswith("l")

        # If symlink and follow=true, stat the target for type info
        target_jc_data = None
        if is_symlink and follow:
            target_stat_result = self._cmd(
                ["stat", "-L", path], task_vars=task_vars, check_mode=False
            )
            # Parse target's stat output
            try:
                target_parsed = jc_parse(
                    "stat", target_stat_result.get("stdout", "")
                )
                if not target_parsed or not isinstance(target_parsed, list):
                    raise AnsibleActionFail(
                        "jc stat parser returned empty result for target"
                    )
                target_jc_data = target_parsed[0]
                if not isinstance(target_jc_data, dict):
                    raise AnsibleActionFail(
                        "jc stat parser returned invalid result for target"
                    )
                # Validate required fields in target data
                if not target_jc_data.get("flags") or not isinstance(
                    target_jc_data.get("flags"), str
                ):
                    raise AnsibleActionFail(
                        "jc stat result for target missing flags field"
                    )
                # Check if target is still a symlink (broken symlink)
                # On some systems, stat -L on broken symlink returns
                # the symlink itself rather than failing
                if target_jc_data["flags"].startswith("l"):
                    # Broken symlink - target doesn't exist
                    return {"exists": False}
            except AnsibleActionFail:
                raise
            except Exception as e:
                raise AnsibleActionFail(
                    f"Failed to parse stat output for target {path}: {e}"
                )

        # Use target's flags if following symlink, else use original
        type_flags = target_jc_data["flags"] if target_jc_data else flags

        # Set file type based on appropriate flags
        stat_result["isdir"] = type_flags.startswith("d")
        stat_result["islnk"] = type_flags.startswith("l")
        stat_result["isreg"] = type_flags.startswith("-")
        stat_result["isblk"] = type_flags.startswith("b")
        stat_result["ischr"] = type_flags.startswith("c")
        stat_result["isfifo"] = type_flags.startswith("p")
        stat_result["issock"] = type_flags.startswith("s")

        # Check executability using test -x (more accurate than parsing)
        test_executable = self._cmd(
            ["test", "-x", path], task_vars=task_vars, check_mode=False
        )
        is_executable = test_executable.get("rc") == 0

        # Mode - convert flags to 4-digit octal
        # When following a symlink, use target's mode. Otherwise use the
        # actual permissions from the file/symlink itself.
        mode_flags = target_jc_data["flags"] if target_jc_data else flags
        stat_result["mode"] = self._parse_mode_from_flags(mode_flags)

        # Permission booleans - rusr, wusr, xusr, rgrp, wgrp, xgrp, etc.
        # When following a symlink, use target's permissions. Otherwise
        # use actual permissions from the file/symlink.
        permission_bools = self._parse_permission_booleans(mode_flags)
        # Override executable with test result for accuracy
        permission_bools["executable"] = is_executable
        stat_result.update(permission_bools)

        # Symlink targets - get immediate and resolved targets
        # Use is_symlink (original) not islnk (may be target type)
        if is_symlink:
            lnk_target = self._get_symlink_target(path, task_vars)
            if lnk_target:
                stat_result["lnk_target"] = lnk_target

            lnk_source = self._get_symlink_source(path, task_vars)
            if lnk_source:
                stat_result["lnk_source"] = lnk_source

        # Owner/group - get names and lookup numeric IDs
        username = jc_data["user"]
        stat_result["pw_name"] = username
        # Try to get numeric uid
        uid_result = self._cmd(
            ["id", "-u", username],
            task_vars=task_vars,
            check_mode=False,
        )
        if uid_result.get("rc") == 0:
            uid_str = uid_result.get("stdout", "").strip()
            if uid_str and uid_str.isdigit():
                stat_result["uid"] = int(uid_str)
        else:
            raise AnsibleActionFail(f"Unable to determine uid of {username}")

        groupname = jc_data["group"]
        stat_result["gr_name"] = groupname
        # Try to get numeric gid
        gid_result = self._cmd(
            ["id", "-g", username] if username else ["id", "-g"],
            task_vars=task_vars,
            check_mode=False,
        )
        if gid_result.get("rc") == 0:
            gid_str = gid_result.get("stdout", "").strip()
            if gid_str and gid_str.isdigit():
                stat_result["gid"] = int(gid_str)
        else:
            raise AnsibleActionFail(f"Unable to determine gid of {groupname}")

        # Unix flags (BSD) - validate it's hex string before converting
        # On BSD systems, default to 0 to match builtin.stat behavior
        if is_bsd:
            stat_result["flags"] = 0  # Default for BSD systems
            unix_flags = jc_data.get("unix_flags")
            if unix_flags and isinstance(unix_flags, str):
                # Only process if it looks like a hex value (not a path)
                if unix_flags.replace("/", "").replace("x", "").isalnum():
                    try:
                        # Remove any 0x prefix if present
                        hex_str = unix_flags.lower().replace("0x", "")
                        # Validate all characters are valid hex digits
                        if all(c in "0123456789abcdef" for c in hex_str):
                            stat_result["flags"] = int(hex_str, 16)
                    except (ValueError, TypeError):
                        # Keep default value 0
                        pass

        # Get checksum if requested (only for regular files)
        if get_checksum and stat_result["isreg"]:
            checksum = self._get_checksum(path, checksum_algorithm, task_vars)
            if checksum:
                stat_result["checksum"] = checksum
            else:
                raise AnsibleActionFail("Checksum is empty")

        # Get MIME type if requested
        if get_mime:
            mime_info = self._get_mime(path, task_vars)
            if mime_info:
                stat_result.update(mime_info)
            else:
                raise AnsibleActionFail("MIME info is empty")

        # Note: generation and version fields are excluded in raw mode
        # These require ioctl/statx system calls not available via
        # stat command. See class docstring for raw mode limitations.

        # Get extended attributes if requested
        if get_attributes:
            # Get filesystem flags
            flags_output = self._get_flags(path, task_vars)
            if flags_output:
                # Set attr_flags to raw flag chars (Linux lsattr)
                attr_flags_raw = self._extract_attr_flags(flags_output)
                if attr_flags_raw:
                    stat_result["attr_flags"] = attr_flags_raw

                # Parse flags into attribute names (Linux only)
                # Skip on BSD/macOS to match builtin.stat behavior
                if attr_flags_raw:  # Only if lsattr format (Linux)
                    attrs = self._normalize_flags(flags_output)
                    if attrs:
                        stat_result["attributes"] = attrs

            # Get extended attributes
            xattrs_output = self._get_xattrs(path, task_vars)
            if xattrs_output:
                attr_names, acl_entries, selinux_val = self._process_xattrs(
                    xattrs_output
                )
                if attr_names:
                    stat_result["xattrs"] = attr_names
                if selinux_val:
                    stat_result["selinux"] = selinux_val
                for acl_entry in acl_entries:
                    self._merge_acl(stat_result, acl_entry)

            # Get ACL information
            acl_info = self._get_acl(path, task_vars)
            if acl_info:
                self._merge_acl(stat_result, acl_info)

        return stat_result

    def _parse_mode_from_flags(self, flags: str) -> str:
        """Convert permission flags to 4-digit octal mode.

        Parses Unix permission flags (e.g., "-rw-r--r--") and converts
        them to 4-digit octal format (e.g., "0644").

        :param str flags: Permission flags string from stat
        :returns str: 4-digit octal mode string
        """
        if not flags or len(flags) < 10:
            return "0000"

        mode = 0

        # Special bits (setuid, setgid, sticky)
        if flags[3] in ("s", "S"):  # setuid
            mode |= 0o4000
        if flags[6] in ("s", "S"):  # setgid
            mode |= 0o2000
        if flags[9] in ("t", "T"):  # sticky
            mode |= 0o1000

        # Owner permissions
        if flags[1] == "r":
            mode |= 0o400
        if flags[2] == "w":
            mode |= 0o200
        if flags[3] in ("x", "s"):
            mode |= 0o100

        # Group permissions
        if flags[4] == "r":
            mode |= 0o040
        if flags[5] == "w":
            mode |= 0o020
        if flags[6] in ("x", "s"):
            mode |= 0o010

        # Other permissions
        if flags[7] == "r":
            mode |= 0o004
        if flags[8] == "w":
            mode |= 0o002
        if flags[9] in ("x", "t"):
            mode |= 0o001

        return f"{mode:04o}"

    def _parse_permission_booleans(self, flags: str) -> Dict[str, bool]:
        """Parse permission booleans from flags string.

        :param str flags: Permission flags string (e.g., "-rw-r--r--")
        :returns Dict[str, bool]: Permission boolean dictionary
        """
        if not flags or len(flags) < 10:
            return {}

        perms: Dict[str, bool] = {}

        # Owner permissions
        perms["rusr"] = flags[1] == "r"
        perms["wusr"] = flags[2] == "w"
        perms["xusr"] = flags[3] in ("x", "s")

        # Group permissions
        perms["rgrp"] = flags[4] == "r"
        perms["wgrp"] = flags[5] == "w"
        perms["xgrp"] = flags[6] in ("x", "s")

        # Other permissions
        perms["roth"] = flags[7] == "r"
        perms["woth"] = flags[8] == "w"
        perms["xoth"] = flags[9] in ("x", "t")

        # Special bits
        perms["isuid"] = flags[3] in ("s", "S")
        perms["isgid"] = flags[6] in ("s", "S")

        # High-level permission flags (simplified)
        perms["readable"] = perms["rusr"]
        perms["writeable"] = perms["wusr"]
        perms["executable"] = perms["xusr"]

        return perms

    def _get_checksum(
        self,
        path: str,
        algorithm: str,
        task_vars: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """Compute file checksum using available hash commands.

        :param str path: File path to checksum
        :param str algorithm: Hash algorithm (md5, sha1, sha224, sha256,
            sha384, sha512)
        :param Optional[Dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Optional[str]: Hex checksum string or None
        """
        # Try GNU coreutils first (Linux)
        cmd_map_gnu = {
            "md5": "md5sum",
            "sha1": "sha1sum",
            "sha224": "sha224sum",
            "sha256": "sha256sum",
            "sha384": "sha384sum",
            "sha512": "sha512sum",
        }

        gnu_cmd = cmd_map_gnu.get(algorithm)
        if gnu_cmd:
            result = self._cmd(
                [gnu_cmd, path], task_vars=task_vars, check_mode=False
            )
            if result.get("rc") == 0:
                stdout = result.get("stdout", "").strip()
                if stdout:
                    # Format: "checksum  filename"
                    parts = stdout.split()
                    if parts:
                        return parts[0]

        # Try BSD/macOS commands
        if algorithm == "md5":
            result = self._cmd(
                ["md5", "-q", path], task_vars=task_vars, check_mode=False
            )
            if result.get("rc") == 0:
                return result.get("stdout", "").strip()

        # Try shasum (available on macOS and some Linux)
        if algorithm in ("sha1", "sha224", "sha256", "sha384", "sha512"):
            algo_num = {
                "sha1": "1",
                "sha224": "224",
                "sha256": "256",
                "sha384": "384",
                "sha512": "512",
            }[algorithm]
            result = self._cmd(
                ["shasum", "-a", algo_num, path],
                task_vars=task_vars,
                check_mode=False,
            )
            if result.get("rc") == 0:
                stdout = result.get("stdout", "").strip()
                if stdout:
                    parts = stdout.split()
                    if parts:
                        return parts[0]

        return None

    def _get_mime(
        self, path: str, task_vars: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, str]]:
        """Detect MIME type and charset.

        :param str path: File path to inspect
        :param Optional[Dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Optional[Dict[str, str]]: Dict with mimetype and
            charset or None
        """
        result = self._cmd(
            ["file", "-b", "--mime", path],
            task_vars=task_vars,
            check_mode=False,
        )
        if result.get("rc") != 0:
            return None

        output = result.get("stdout", "").strip()
        if not output:
            return None

        # Parse: "text/plain; charset=us-ascii"
        mime_info: Dict[str, str] = {}
        parts = output.split(";", 1)
        if parts:
            mimetype = parts[0].strip()
            # Normalize application/x-not-regular-file to "unknown" to
            # match builtin.stat behavior on OpenBSD
            if mimetype == "application/x-not-regular-file":
                mime_info["mimetype"] = "unknown"
            else:
                mime_info["mimetype"] = mimetype

        if len(parts) > 1:
            charset_part = parts[1].strip()
            if charset_part.startswith("charset="):
                mime_info["charset"] = charset_part[8:].strip()

        # Always include charset, default to "unknown" if not found
        if "charset" not in mime_info:
            mime_info["charset"] = "unknown"

        return mime_info if mime_info else None

    def run(
        self,
        tmp: Optional[str] = None,
        task_vars: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute stat and return file metadata.

        :param Optional[str] tmp: Unused temporary directory path
        :param Optional[Dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Dict[str, Any]: Result with file metadata under 'stat'
            key
        :raises AnsibleActionFail: When invalid arguments are provided
        """
        task_vars = task_vars or {}
        tmp = None

        result = super().run(tmp, task_vars)
        result["invocation"] = self._task.args.copy()
        result["changed"] = False

        argument_spec = {
            "path": {
                "type": "str",
                "required": True,
                "aliases": ["dest", "name"],
            },
            "follow": {"type": "bool", "default": False},
            "get_checksum": {"type": "bool", "default": True},
            "get_mime": {
                "type": "bool",
                "default": True,
                "aliases": ["mime", "mime_type", "mime-type"],
            },
            "get_attributes": {
                "type": "bool",
                "default": True,
                "aliases": ["attr", "attributes"],
            },
            "checksum_algorithm": {
                "type": "str",
                "default": "sha1",
                "choices": [
                    "md5",
                    "sha1",
                    "sha224",
                    "sha256",
                    "sha384",
                    "sha512",
                ],
                "aliases": ["checksum", "checksum_algo"],
            },
            "_force_raw": {"type": "bool", "default": False},
        }
        validation_result, new_module_args = self.validate_argument_spec(
            argument_spec=argument_spec
        )
        self.force_raw = new_module_args.pop("_force_raw")

        # Try ansible.builtin.stat first
        if not self.force_raw:
            builtin_module_args = new_module_args.copy()
            ansible_stat_mod = self._execute_module(
                module_name="ansible.builtin.stat",
                module_args=builtin_module_args,
                task_vars=task_vars,
            )
            ansible_stat_mod.pop("invocation", None)

            if not self._is_interpreter_missing(ansible_stat_mod):
                result.update(ansible_stat_mod)
                result["raw"] = False
            else:
                host = self._get_inventory_hostname(task_vars)
                self._display.warning(
                    f"[{host}] Ansible command module failed; "
                    "falling back to raw command."
                )
                self.force_raw = True

        if self.force_raw:
            # Fall back to stat command with jc
            result = {
                "changed": False,
                "raw": True,
            }
            result["stat"] = self._stat_with_jc(new_module_args)

        self._remove_tmp_path(self._connection._shell.tmpdir)

        return result
