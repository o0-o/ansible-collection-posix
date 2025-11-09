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

"""Base class for action plugins that need stat operations."""

from __future__ import annotations

import re
from numbers import Number
from typing import Any, Dict, List, Optional, Tuple

from ansible.module_utils.common.text.converters import to_text

from ansible_collections.o0_o.posix.plugins.module_utils import (
    device_from_hex_major_minor,
    device_from_major_minor,
    device_value,
    jc_parse,
    PosixActionBase,
)


class ReadPosixActionBase(PosixActionBase):
    """Base class for stat and read plugins with shared methods."""

    def _slurp(
        self,
        src: str,
        encoding: str = "utf-8",
        task_vars: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run the fallback-compatible slurp64 action plugin.

        Reads remote files using the o0_o.posix.slurp64 action plugin
        which provides Python-free fallback capability.

        :param str src: Path to the file on the remote host
        :param str encoding: File encoding (default: utf-8)
        :param Optional[Dict[str, Any]] task_vars: Task variables
        :returns Dict[str, Any]: Result dictionary from slurp64
        """
        return self._run_action(
            "o0_o.posix.slurp64",
            {"src": src, "encoding": encoding},
            task_vars=task_vars,
        )

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

        Uses batched command execution to minimize SSH round trips,
        reducing latency from 16-20 individual commands to 2-3 batches.

        :param Optional[Dict[str, Any]] module_args: Module arguments
            dictionary containing command parameters
        :param Optional[Dict[str, Any]] task_vars: Task variables
            dictionary
        :returns Dict[str, Any]: Result dictionary with stat
            information
        :raises RuntimeError: When batch commands fail or parsing fails
        :raises ValueError: When jc output validation fails
        """
        path = module_args["path"]
        follow = module_args["follow"]
        get_checksum = module_args["get_checksum"]
        get_mime = module_args["get_mime"]
        get_attributes = module_args["get_attributes"]
        checksum_algorithm = module_args["checksum_algorithm"]
        stat_result = {"exists": False}

        # BATCH 1: Initial discovery - run these commands together
        # to gather basic file information and determine file type
        batch1_commands = [
            ["stat", path],  # Main stat output
            ["readlink", path],  # Symlink target (may fail)
            ["readlink", "-f", path],  # Resolved target (may fail)
            ["test", "-x", path],  # Executability check
        ]

        # Add MIME type command if requested
        if get_mime:
            batch1_commands.append(["file", "-b", "--mime", path])

        batch1_result = self._run(
            commands=batch1_commands,
            task_vars=task_vars,
            check_mode=False,
        )

        if batch1_result.get("failed"):
            raise RuntimeError(
                f"Batch 1 commands failed: {batch1_result.get('msg')}"
            )

        # Extract individual command results
        results = batch1_result.get("results", [])
        expected_count = 5 if get_mime else 4
        if len(results) < expected_count:
            raise ValueError(
                f"Expected {expected_count} results from batch 1, "
                f"got {len(results)}"
            )

        stat_output_result = results[0]
        readlink_result = results[1]
        readlink_f_result = results[2]
        test_x_result = results[3]
        mime_result = results[4] if get_mime else None

        # Check if file exists (stat command succeeded)
        if stat_output_result.get("rc") != 0:
            # File doesn't exist or other error
            return stat_result

        stat_result = {
            "exists": True,
            # Platform-specific fields - set defaults for
            # compatibility with builtin.stat
            "attr_flags": "",
            "attributes": [],
        }

        self._display.vvv(stat_output_result.get("stdout"))

        # Parse with jc
        try:
            parsed = jc_parse("stat", stat_output_result.get("stdout", ""))
        except Exception as e:
            raise ValueError(f"Failed to parse stat output for {path}: {e}")

        # jc audit
        if (
            not parsed
            or not isinstance(parsed, list)
            or len(parsed) == 0
            or not isinstance(parsed[0], dict)
        ):
            raise ValueError("jc stat parser returned empty result")
        jc_data = parsed[0]
        self._display.vvv(to_text(jc_data))

        for field in ["file", "flags", "user", "group"]:
            if jc_data.get(field) is None or not isinstance(
                jc_data.get(field), str
            ):
                raise ValueError(
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
                raise ValueError(
                    f"jc stat result missing {field} field (number): "
                    f"{to_text(value)}"
                )

        # birth_time_epoch is optional - not all systems support it
        birth_time = jc_data.get("birth_time_epoch")
        if birth_time is not None and not isinstance(birth_time, Number):
            raise ValueError(
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
                raise ValueError(
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
            raise ValueError(f"jc flags result invalid: {flags}")

        is_symlink = flags.startswith("l")
        username = jc_data["user"]
        groupname = jc_data["group"]

        # BATCH 2: Commands that depend on stat parsing
        # Always need uid/gid lookups
        batch2_commands = [
            ["id", "-u", username],
            ["id", "-g", username] if username else ["id", "-g"],
        ]

        # Add stat -L if following symlink
        batch2_stat_l_idx = None
        if is_symlink and follow:
            batch2_stat_l_idx = len(batch2_commands)
            batch2_commands.append(["stat", "-L", path])

        # Add device type check if block or char device
        batch2_device_idx = None
        file_type_char = flags[0]
        if file_type_char in ("b", "c"):
            batch2_device_idx = len(batch2_commands)
            batch2_commands.append(["stat", "-c", "%t,%T", path])

        # Execute batch 2
        batch2_result = self._run(
            commands=batch2_commands,
            task_vars=task_vars,
            check_mode=False,
        )

        if batch2_result.get("failed"):
            raise ValueError(
                f"Batch 2 commands failed: {batch2_result.get('msg')}"
            )

        batch2_results = batch2_result.get("results", [])
        uid_result = batch2_results[0]
        gid_result = batch2_results[1]

        # Set device_type using batch2 device result if available
        device_result_for_type = None
        if batch2_device_idx is not None:
            device_result_for_type = batch2_results[batch2_device_idx]
        stat_result["device_type"] = self._stat_device_type(
            jc_data, device_result=device_result_for_type
        )

        # If symlink and follow=true, stat the target for type info
        target_jc_data = None
        if is_symlink and follow:
            # Get result from batch 2
            if batch2_stat_l_idx is None:
                raise ValueError("stat -L should have been in batch 2")
            target_stat_result = batch2_results[batch2_stat_l_idx]

            # Parse target's stat output
            try:
                target_parsed = jc_parse(
                    "stat", target_stat_result.get("stdout", "")
                )
                if not target_parsed or not isinstance(target_parsed, list):
                    raise ValueError(
                        "jc stat parser returned empty result for target"
                    )
                target_jc_data = target_parsed[0]
                if not isinstance(target_jc_data, dict):
                    raise ValueError(
                        "jc stat parser returned invalid result for target"
                    )
                # Validate required fields in target data
                if not target_jc_data.get("flags") or not isinstance(
                    target_jc_data.get("flags"), str
                ):
                    raise ValueError(
                        "jc stat result for target missing flags field"
                    )
                # Check if target is still a symlink (broken symlink)
                # On some systems, stat -L on broken symlink returns
                # the symlink itself rather than failing
                if target_jc_data["flags"].startswith("l"):
                    # Broken symlink - target doesn't exist
                    return {"exists": False}
            except ValueError:
                raise
            except Exception as e:
                raise ValueError(
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
        # Use result from batch 1
        is_executable = test_x_result.get("rc") == 0

        # Mode - convert flags to 4-digit octal
        # When following a symlink, use target's mode. Otherwise use the
        # actual permissions from the file/symlink itself.
        mode_flags = target_jc_data["flags"] if target_jc_data else flags
        stat_result["mode"] = self._stat_mode_from_flags(mode_flags)

        # Permission booleans - rusr, wusr, xusr, rgrp, wgrp, xgrp, etc.
        # When following a symlink, use target's permissions. Otherwise
        # use actual permissions from the file/symlink.
        permission_bools = self._stat_permission_booleans(mode_flags)
        # Override executable with test result for accuracy
        permission_bools["executable"] = is_executable
        stat_result.update(permission_bools)

        # Symlink targets - get immediate and resolved targets
        # Use is_symlink (original) not islnk (may be target type)
        # Use results from batch 1
        if is_symlink:
            if readlink_result.get("rc") == 0:
                lnk_target = readlink_result.get("stdout", "").strip()
                if lnk_target:
                    stat_result["lnk_target"] = lnk_target

            if readlink_f_result.get("rc") == 0:
                lnk_source = readlink_f_result.get("stdout", "").strip()
                if lnk_source:
                    stat_result["lnk_source"] = lnk_source

        # Owner/group - get names and lookup numeric IDs
        # (username and groupname extracted earlier from jc_data)
        stat_result["pw_name"] = username
        stat_result["gr_name"] = groupname

        # Use uid/gid results from batch 2
        if uid_result.get("rc") == 0:
            uid_str = uid_result.get("stdout", "").strip()
            if uid_str and uid_str.isdigit():
                stat_result["uid"] = int(uid_str)
        else:
            raise ValueError(f"Unable to determine uid of {username}")

        if gid_result.get("rc") == 0:
            gid_str = gid_result.get("stdout", "").strip()
            if gid_str and gid_str.isdigit():
                stat_result["gid"] = int(gid_str)
        else:
            raise ValueError(f"Unable to determine gid of {groupname}")

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
                # Warn if checksum algorithm not available on target
                host = self._get_inventory_hostname(task_vars)
                self._display.warning(
                    f"[{host}] Checksum algorithm '{checksum_algorithm}' "
                    f"not available on target system. Checksum field will "
                    f"be omitted."
                )

        # Get MIME type if requested
        # Use result from batch 1
        if get_mime and mime_result:
            if mime_result.get("rc") == 0:
                output = mime_result.get("stdout", "").strip()
                if output:
                    # Parse: "text/plain; charset=us-ascii"
                    mime_info: Dict[str, str] = {}
                    parts = output.split(";", 1)
                    if parts:
                        mimetype = parts[0].strip()
                        # Normalize application/x-not-regular-file
                        # to "unknown" (match builtin.stat on OpenBSD)
                        if mimetype == "application/x-not-regular-file":
                            mime_info["mimetype"] = "unknown"
                        else:
                            mime_info["mimetype"] = mimetype

                    if len(parts) > 1:
                        charset_part = parts[1].strip()
                        if charset_part.startswith("charset="):
                            mime_info["charset"] = charset_part[8:].strip()

                    # Always include charset, default to "unknown"
                    if "charset" not in mime_info:
                        mime_info["charset"] = "unknown"

                    if mime_info:
                        stat_result.update(mime_info)
                    else:
                        raise ValueError("MIME info is empty")
                else:
                    raise ValueError("MIME output is empty")
            else:
                raise ValueError(
                    f"MIME command failed: {mime_result.get('stderr', '')}"
                )

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

        # Try OpenBSD commands (sha1, sha256, sha512 without -q)
        # Output format: "SHA256 (file) = checksum"
        if algorithm in ("sha1", "sha256", "sha512"):
            result = self._cmd(
                [algorithm, path], task_vars=task_vars, check_mode=False
            )
            if result.get("rc") == 0:
                stdout = result.get("stdout", "").strip()
                if stdout and "=" in stdout:
                    # Parse "SHA256 (file) = checksum"
                    checksum = stdout.split("=", 1)[1].strip()
                    if checksum:
                        return checksum

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

    def _stat_device_type(
        self,
        jc_data: Dict[str, Any],
        device_result: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Get device type (rdev) with intelligent fallback detection.

        Determines the device type value based on file type and
        available data. For regular files and similar types, returns 0.
        For device files, uses the provided device_result from batched
        command execution.

        :param Dict[str, Any] jc_data: Parsed jc stat output
        :param Optional[Dict[str, Any]] device_result: Result from
            stat -c "%t,%T" command (if device file)
        :returns int: Device type number (rdev), 0 for non-device
            files
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

        # Block or character device - use provided device_result
        if file_type_char in ("b", "c") and device_result:
            if device_result.get("rc") == 0:
                output = device_result.get("stdout", "").strip()
                if output:
                    rdev_int = device_from_hex_major_minor(output)
                    if rdev_int is not None:
                        return rdev_int

        # Default fallback
        return 0

    def _stat_mode_from_flags(self, flags: str) -> str:
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

    def _stat_permission_booleans(self, flags: str) -> Dict[str, bool]:
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

    def _validate_jc_stat_result(self, jc_data: Dict[str, Any]) -> None:
        """Validate that jc stat result has required fields.

        :param Dict[str, Any] jc_data: Parsed jc stat output
        :raises ValueError: If required fields are missing or invalid
        """
        for field in ["file", "flags", "user", "group"]:
            if jc_data.get(field) is None or not isinstance(
                jc_data.get(field), str
            ):
                raise ValueError(
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
                raise ValueError(
                    f"jc stat result missing {field} field (number): {value}"
                )

        # birth_time_epoch is optional - not all systems support it
        birth_time = jc_data.get("birth_time_epoch")
        if birth_time is not None and not isinstance(birth_time, Number):
            raise ValueError(
                f"jc stat result has invalid birth_time_epoch: "
                f"{birth_time}"
            )

        # Validate flags format
        flags = jc_data["flags"]
        flags_re = re.compile(r"^[\-dlcbsp][-rwxSsTt]{9}$")
        if not flags_re.match(flags):
            raise ValueError(f"jc flags result invalid: {flags}")

    def _get_acl(
        self, path: str, task_vars: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Retrieve ACL information for a path.

        :param str path: Path to get ACLs for
        :param Optional[Dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Optional[Dict[str, Any]]: ACL metadata with type or None
        """
        result = self._cmd(["getfacl", "-p", path], task_vars=task_vars)
        if result.get("rc") == 0:
            output = (result.get("stdout") or "").strip()
            if output:
                return {"type": "posix", "text": output}
        # macOS fallback: ls -le prints ACLs
        alt = self._cmd(["ls", "-le", path], task_vars=task_vars)
        if alt.get("rc") == 0:
            output = (alt.get("stdout") or "").strip()
            if output:
                lines = output.splitlines()
                prefixes = tuple(f"{i}:" for i in range(10))
                if any(
                    line.lstrip().startswith(prefixes) for line in lines[1:]
                ):
                    return {"type": "macos", "text": output}
        return None

    def _get_xattrs(
        self, path: str, task_vars: Optional[Dict[str, Any]]
    ) -> Optional[str]:
        """Retrieve extended attributes for a path.

        :param str path: Path to get extended attributes for
        :param Optional[Dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Optional[str]: Extended attributes or None if
            unavailable
        """
        result = self._cmd(
            ["getfattr", "--absolute-names", "-d", path], task_vars=task_vars
        )
        if result.get("rc") == 0:
            output = (result.get("stdout") or "").strip()
            if output:
                return output
        # macOS fallback: xattr -l
        alt = self._cmd(["xattr", "-l", path], task_vars=task_vars)
        if alt.get("rc") == 0:
            output = (alt.get("stdout") or "").strip()
            if output:
                return output
        return None

    def _get_flags(
        self, path: str, task_vars: Optional[Dict[str, Any]]
    ) -> Optional[str]:
        """Retrieve filesystem flags for a path.

        :param str path: Path to get flags for
        :param Optional[Dict[str, Any]] task_vars: Available Ansible
            variables
        :returns Optional[str]: Filesystem flags or None if unavailable
        """
        result = self._cmd(["lsattr", "-d", path], task_vars=task_vars)
        if result.get("rc") != 0:
            alt = self._cmd(["ls", "-ldO", path], task_vars=task_vars)
            if alt.get("rc") != 0:
                return None
            stdout = alt.get("stdout") or ""
            parts = stdout.split()
            if len(parts) >= 5:
                flags = parts[4]
                if flags != "-":
                    return flags
            return None
        stdout = result.get("stdout") or ""
        parts = stdout.split()
        if not parts:
            return None
        return parts[0]

    def _process_xattrs(
        self,
        source: Optional[object],
    ) -> Tuple[List[str], List[Dict[str, Any]], Optional[str]]:
        """Normalize xattr sources into names and specialised records.

        :param Optional[object] source: Extended attributes from xattr
            command
        :returns Tuple[List[str], List[Dict[str, Any]], Optional[str]]:
            Tuple of (attribute names, ACL records, SELinux value)
        """
        names: List[str] = []
        acl_records: Dict[str, Dict[str, Any]] = {}
        selinux_value: Optional[str] = None

        def place_acl(record_type: str) -> Dict[str, Any]:
            entry = acl_records.setdefault(record_type, {"type": record_type})
            return entry

        def handle(name: str, value: Optional[str]) -> None:
            nonlocal selinux_value
            key = name.strip()
            if not key:
                return
            lowered = key.lower()
            if lowered == "system.posix_acl_access":
                return
            if lowered == "system.posix_acl_default":
                return
            if lowered in {"com.apple.acl.text", "com.apple.security.acl"}:
                entry = place_acl("macos_xattr")
                if value is not None and "text" not in entry:
                    entry["text"] = value
                return
            if lowered in {"system.nfs4_acl", "nfs4_acl"}:
                entry = place_acl("nfs4_xattr")
                if value is not None and "text" not in entry:
                    entry["text"] = value
                return
            if lowered == "security.selinux":
                if value and selinux_value is None:
                    selinux_value = value
                return
            names.append(key)

        if isinstance(source, dict):
            for key, value in source.items():
                if isinstance(key, bytes):
                    key_obj = key.decode("utf-8", "ignore")
                else:
                    key_obj = str(key)
                value_str = None
                if value is not None:
                    if isinstance(value, bytes):
                        value_str = value.decode("utf-8", "ignore")
                    else:
                        value_str = str(value)
                handle(key_obj, value_str)
        elif isinstance(source, str):
            for line in source.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if ":" in stripped and "=" not in stripped:
                    key, raw_val = stripped.split(":", 1)
                    handle(key, raw_val.strip())
                    continue
                if "=" in stripped:
                    key, raw_val = stripped.split("=", 1)
                    handle(key, raw_val.strip().strip('"').strip("'"))
                    continue
                handle(stripped, None)
        elif source is not None:
            handle(str(source), None)

        names = sorted(set(names))
        acl_list = [value for value in acl_records.values() if len(value) > 1]
        return names, acl_list, selinux_value

    def _merge_acl(self, info: Dict[str, Any], entry: Dict[str, Any]) -> None:
        """Merge ACL details into result dictionary with type tracking.

        :param Dict[str, Any] info: Stat dictionary to merge ACL into
        :param Dict[str, Any] entry: ACL entry to merge
        """
        if not entry:
            return

        entry_type = entry.get("type")
        existing = info.get("acl")

        if entry_type == "posix_xattr":
            if isinstance(existing, dict) and existing.get("type") == "posix":
                return
            if isinstance(existing, list) and any(
                isinstance(item, dict) and item.get("type") == "posix"
                for item in existing
            ):
                return

        if existing is None:
            info["acl"] = entry.copy()
            return

        if isinstance(existing, dict):
            existing_type = existing.get("type")
            if entry_type and existing_type == entry_type:
                merged = existing.copy()
                for key, value in entry.items():
                    if key in {"type"}:
                        continue
                    if key not in merged:
                        merged[key] = value
                info["acl"] = merged
                return

            info["acl"] = [existing.copy(), entry.copy()]
            return

        if isinstance(existing, list):
            if entry_type:
                for idx, item in enumerate(existing):
                    if (
                        isinstance(item, dict)
                        and item.get("type") == entry_type
                    ):
                        merged = item.copy()
                        for key, value in entry.items():
                            if key in {"type"}:
                                continue
                            if key not in merged:
                                merged[key] = value
                        existing[idx] = merged
                        info["acl"] = existing
                        return
            existing.append(entry.copy())
            info["acl"] = existing
            return

        # Existing value is plain string; convert to structured form.
        info["acl"] = [
            {"type": "unknown", "text": str(existing)},
            entry.copy(),
        ]

    def _extract_attr_flags(self, value: str) -> str:
        """Extract raw flag characters from lsattr output.

        Converts "--------------e-------" to "e" (just the set flags).
        For BSD/macOS format, returns empty string as it doesn't use
        single-character flags.

        :param str value: Raw lsattr/ls output
        :returns str: Flag characters that are set
        """
        flags_str = value.strip()
        if not flags_str or flags_str == "-":
            return ""

        # BSD/macOS format - doesn't use attr_flags field
        if "," in flags_str or any(
            word.isalpha() and len(word) > 1 for word in flags_str.split()
        ):
            return ""

        # Linux lsattr format - extract non-dash characters
        flag_chars = "".join(
            char for char in flags_str if char not in ("-", " ")
        )
        return flag_chars

    def _normalize_flags(self, value: str) -> List[str]:
        """Parse filesystem flags into attribute names.

        Handles multiple formats:
        - Linux lsattr: "--------------e-------" → ["extents"]
        - BSD/macOS: "restricted,hidden" or "restricted hidden" → as-is

        :param str value: Raw flags string
        :returns List[str]: List of attribute names
        """
        flags_str = value.strip()
        if not flags_str or flags_str == "-":
            return []

        # BSD/macOS format: comma or space separated words
        if "," in flags_str:
            return [
                flag.strip() for flag in flags_str.split(",") if flag.strip()
            ]

        # Check if readable words (BSD format without commas)
        if any(word.isalpha() and len(word) > 1 for word in flags_str.split()):
            return [flag.strip() for flag in flags_str.split() if flag.strip()]

        # Linux lsattr format: single-character flags
        flag_map = {
            "a": "append_only",
            "c": "compressed",
            "d": "no_dump",
            "e": "extents",
            "i": "immutable",
            "j": "data_journaling",
            "s": "secure_deletion",
            "t": "no_tail_merging",
            "u": "undeletable",
            "A": "no_atime",
            "D": "synchronous_directory",
            "S": "synchronous_updates",
            "T": "top_of_directory_hierarchy",
            "C": "no_copy_on_write",
            "E": "encrypted",
            "I": "indexed_directory",
            "N": "inline_data",
            "P": "project_hierarchy",
            "V": "verity",
        }

        attributes = []
        for char in flags_str:
            if char in flag_map:
                attributes.append(flag_map[char])

        return attributes
