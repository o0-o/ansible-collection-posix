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

"""Unit tests for compliance_utils module_utils."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ansible_collections.o0_o.posix.plugins.module_utils.compliance_utils import (  # noqa: E501
    SUS,
    POSIX,
    XSH,
    XCU,
    XSI,
    _process_getconf_results,
    _verify_required_commands,
    _determine_compliance_levels,
    _build_command_inventory,
    process_compliance_commands_result,
)


class TestConstants:
    """Tests for standard metadata constants."""

    def test_sus_metadata(self) -> None:
        """Test SUS constant has required fields."""
        assert SUS["name"] == "Single UNIX Specification"
        assert SUS["abbreviation"] == "SUS"
        assert "description" in SUS

    def test_posix_metadata(self) -> None:
        """Test POSIX constant has required fields."""
        assert POSIX["name"] == "Portable Operating System Interface"
        assert POSIX["abbreviation"] == "POSIX"
        assert "description" in POSIX

    def test_xsh_metadata(self) -> None:
        """Test XSH constant has required fields."""
        assert XSH["abbreviation"] == "XSH"
        assert "name" in XSH

    def test_xcu_metadata(self) -> None:
        """Test XCU constant has required fields."""
        assert XCU["abbreviation"] == "XCU"
        assert "name" in XCU

    def test_xsi_metadata(self) -> None:
        """Test XSI constant has required fields."""
        assert XSI["abbreviation"] == "XSI"
        assert "name" in XSI


class TestProcessGetconfResults:
    """Tests for _process_getconf_results function."""

    def test_merges_valid_xsh_version(self) -> None:
        """Test merging valid XSH version into compliance dict."""
        compliance = {"xsh": {}, "xsi": {}, "xcu": {}}
        processed_cmds = {
            "posix_xsh_version": {
                "xsh": {"supported": True, "version": {"id": "2008"}}
            },
            "posix_xopen_support": {"xsi": {"supported": False}},
            "posix_xopen_version": None,
            "posix_xcu_version": None,
        }
        cmd_errors = {
            "posix_xsh_version": None,
            "posix_xopen_support": None,
        }
        commands_result = {}

        errors = _process_getconf_results(
            processed_cmds, cmd_errors, commands_result, compliance
        )

        assert errors == []
        assert compliance["xsh"]["supported"] is True
        assert compliance["xsh"]["version"]["id"] == "2008"

    def test_error_when_getconf_returns_none(self) -> None:
        """Test error generated when getconf returns None."""
        compliance = {"xsh": {}, "xsi": {}, "xcu": {}}
        processed_cmds = {
            "posix_xsh_version": None,
            "posix_xopen_support": {"xsi": {"supported": False}},
            "posix_xopen_version": None,
            "posix_xcu_version": None,
        }
        cmd_errors = {
            "posix_xsh_version": None,
            "posix_xopen_support": None,
        }
        commands_result = {
            "posix_xsh_version": {"command": "getconf _POSIX_VERSION"},
        }

        errors = _process_getconf_results(
            processed_cmds, cmd_errors, commands_result, compliance
        )

        assert len(errors) == 1
        assert "getconf _POSIX_VERSION" in str(errors[0])
        assert "did not return a valid result" in str(errors[0])

    def test_handles_tuple_command(self) -> None:
        """Test command tuple is joined into string for error message."""
        compliance = {"xsh": {}, "xsi": {}, "xcu": {}}
        processed_cmds = {
            "posix_xsh_version": None,
            "posix_xopen_support": {"xsi": {"supported": False}},
            "posix_xopen_version": None,
            "posix_xcu_version": None,
        }
        cmd_errors = {
            "posix_xsh_version": None,
            "posix_xopen_support": None,
        }
        commands_result = {
            "posix_xsh_version": {
                "command": ("getconf", "_POSIX_VERSION"),
            },
        }

        errors = _process_getconf_results(
            processed_cmds, cmd_errors, commands_result, compliance
        )

        assert len(errors) == 1
        assert "getconf _POSIX_VERSION" in str(errors[0])

    def test_extends_getconf_errors(self) -> None:
        """Test parser errors are extended to error list."""
        compliance = {"xsh": {}, "xsi": {}, "xcu": {}}
        parser_error = ValueError("Parser error")
        processed_cmds = {
            "posix_xsh_version": None,
            "posix_xopen_support": {"xsi": {"supported": False}},
            "posix_xopen_version": None,
            "posix_xcu_version": None,
        }
        cmd_errors = {
            "posix_xsh_version": [parser_error],
            "posix_xopen_support": None,
        }
        commands_result = {
            "posix_xsh_version": {"command": "getconf"},
        }

        errors = _process_getconf_results(
            processed_cmds, cmd_errors, commands_result, compliance
        )

        assert len(errors) == 2
        assert parser_error in errors

    def test_detects_xsi_support_mismatch(self) -> None:
        """Test error on XSI support mismatch between getconf vars."""
        compliance = {"xsh": {}, "xsi": {"supported": True}, "xcu": {}}
        processed_cmds = {
            "posix_xsh_version": {"xsh": {"supported": True}},
            "posix_xopen_support": {"xsi": {"supported": True}},
            "posix_xopen_version": {
                "xsi": {"supported": False},
                "xsh": {"version": None},
            },
            "posix_xcu_version": None,
        }
        cmd_errors = {
            "posix_xsh_version": None,
            "posix_xopen_support": None,
        }
        commands_result = {}

        errors = _process_getconf_results(
            processed_cmds, cmd_errors, commands_result, compliance
        )

        assert any("XSI support mismatch" in str(e) for e in errors)

    def test_detects_xsh_version_mismatch(self) -> None:
        """Test error on XSH version mismatch between getconf vars."""
        compliance = {
            "xsh": {"version": {"id": "2008"}},
            "xsi": {"supported": True},
            "xcu": {},
        }
        processed_cmds = {
            "posix_xsh_version": {
                "xsh": {"supported": True, "version": {"id": "2008"}}
            },
            "posix_xopen_support": {"xsi": {"supported": True}},
            "posix_xopen_version": {
                "xsi": {"supported": True},
                "xsh": {"version": {"id": "2001"}},
            },
            "posix_xcu_version": None,
        }
        cmd_errors = {
            "posix_xsh_version": None,
            "posix_xopen_support": None,
        }
        commands_result = {}

        errors = _process_getconf_results(
            processed_cmds, cmd_errors, commands_result, compliance
        )

        assert any("XSH version mismatch" in str(e) for e in errors)

    def test_detects_posix_xcu_version_mismatch(self) -> None:
        """Test error on XCU version mismatch."""
        compliance = {
            "xsh": {},
            "xsi": {},
            "xcu": {"version": {"id": "2008"}},
        }
        processed_cmds = {
            "posix_xsh_version": {"xsh": {"supported": True}},
            "posix_xopen_support": {"xsi": {"supported": False}},
            "posix_xopen_version": None,
            "posix_xcu_version": {
                "xcu": {"version": {"id": "2001"}},
            },
        }
        cmd_errors = {
            "posix_xsh_version": None,
            "posix_xopen_support": None,
        }
        commands_result = {}

        errors = _process_getconf_results(
            processed_cmds, cmd_errors, commands_result, compliance
        )

        assert any("XCU version mismatch" in str(e) for e in errors)

    def test_detects_xcu_support_mismatch(self) -> None:
        """Test error on XCU support mismatch."""
        compliance = {
            "xsh": {},
            "xsi": {},
            "xcu": {"supported": True},
        }
        processed_cmds = {
            "posix_xsh_version": {"xsh": {"supported": True}},
            "posix_xopen_support": {"xsi": {"supported": False}},
            "posix_xopen_version": None,
            "posix_xcu_version": {
                "xcu": {"supported": False},
            },
        }
        cmd_errors = {
            "posix_xsh_version": None,
            "posix_xopen_support": None,
        }
        commands_result = {}

        errors = _process_getconf_results(
            processed_cmds, cmd_errors, commands_result, compliance
        )

        assert any("XCU support mismatch" in str(e) for e in errors)

    def test_merges_xcu_without_existing(self) -> None:
        """Test XCU merging when no existing xcu in compliance."""
        compliance = {"xsh": {}, "xsi": {}}
        processed_cmds = {
            "posix_xsh_version": {"xsh": {"supported": True}},
            "posix_xopen_support": {"xsi": {"supported": False}},
            "posix_xopen_version": None,
            "posix_xcu_version": {
                "xcu": {"supported": True, "version": {"id": "2008"}},
            },
        }
        cmd_errors = {
            "posix_xsh_version": None,
            "posix_xopen_support": None,
        }
        commands_result = {}

        errors = _process_getconf_results(
            processed_cmds, cmd_errors, commands_result, compliance
        )

        assert errors == []
        assert compliance["xcu"]["supported"] is True


class TestVerifyRequiredCommands:
    """Tests for _verify_required_commands function."""

    def test_all_commands_present(self) -> None:
        """Test no errors when all required commands are present."""
        compliance = {
            "xcu": {"supported": True},
            "xsi": {"supported": True},
        }
        xcu_cmds = {"cat": "/bin/cat", "grep": "/usr/bin/grep"}
        xsi_cmds = {"getconf": "/usr/bin/getconf"}

        xcu_support, xsi_support, errors = _verify_required_commands(
            compliance, xcu_cmds, xsi_cmds
        )

        assert xcu_support is True
        assert xsi_support is True
        assert errors == []

    def test_missing_xcu_commands_revokes_support(self) -> None:
        """Test XCU support revoked when required commands missing."""
        compliance = {
            "xcu": {"supported": True},
            "xsi": {"supported": False},
        }
        xcu_cmds = {"cat": "/bin/cat", "missing_cmd": None}
        xsi_cmds = {"getconf": "/usr/bin/getconf"}

        xcu_support, xsi_support, errors = _verify_required_commands(
            compliance, xcu_cmds, xsi_cmds
        )

        assert xcu_support is False
        assert compliance["xcu"]["supported"] is False
        assert len(errors) == 1
        assert "missing_cmd" in str(errors[0])

    def test_missing_xsi_commands_revokes_support(self) -> None:
        """Test XSI support revoked when required commands missing."""
        compliance = {
            "xcu": {"supported": True},
            "xsi": {"supported": True},
        }
        xcu_cmds = {"cat": "/bin/cat"}
        xsi_cmds = {"getconf": None, "ipcs": None}

        xcu_support, xsi_support, errors = _verify_required_commands(
            compliance, xcu_cmds, xsi_cmds
        )

        assert xsi_support is False
        assert compliance["xsi"]["supported"] is False
        assert len(errors) == 1
        assert "getconf" in str(errors[0]) or "ipcs" in str(errors[0])

    def test_no_error_when_unsupported_and_missing(self) -> None:
        """Test no error when already unsupported and commands missing."""
        compliance = {
            "xcu": {"supported": False},
            "xsi": {"supported": False},
        }
        xcu_cmds = {"missing": None}
        xsi_cmds = {"getconf": None}

        xcu_support, xsi_support, errors = _verify_required_commands(
            compliance, xcu_cmds, xsi_cmds
        )

        assert xcu_support is False
        assert xsi_support is False
        assert errors == []


class TestDetermineComplianceLevels:
    """Tests for _determine_compliance_levels function."""

    def test_full_posix_compliance(self) -> None:
        """Test POSIX supported when both XSH and XCU supported."""
        compliance = {
            "posix": {},
            "sus": {},
            "xsi": {"supported": False},
        }

        _determine_compliance_levels(compliance, True, True, False)

        assert compliance["posix"]["supported"] is True
        assert compliance["sus"]["supported"] is False

    def test_partial_posix_xsh_only(self) -> None:
        """Test partial POSIX when only XSH supported."""
        compliance = {
            "posix": {},
            "sus": {},
            "xsi": {"supported": False},
        }

        _determine_compliance_levels(compliance, True, False, False)

        assert compliance["posix"]["supported"] == "partial"

    def test_partial_posix_xcu_only(self) -> None:
        """Test partial POSIX when only XCU supported."""
        compliance = {
            "posix": {},
            "sus": {},
            "xsi": {"supported": False},
        }

        _determine_compliance_levels(compliance, False, True, False)

        assert compliance["posix"]["supported"] == "partial"

    def test_no_posix_compliance(self) -> None:
        """Test POSIX unsupported when neither XSH nor XCU supported."""
        compliance = {
            "posix": {},
            "sus": {},
            "xsi": {"supported": False},
        }

        _determine_compliance_levels(compliance, False, False, False)

        assert compliance["posix"]["supported"] is False

    def test_full_sus_compliance(self) -> None:
        """Test SUS supported when POSIX and XSI supported."""
        compliance = {
            "posix": {},
            "sus": {},
            "xsi": {"supported": True, "version": {"issue": 7.0}},
        }

        _determine_compliance_levels(compliance, True, True, True)

        assert compliance["posix"]["supported"] is True
        assert compliance["sus"]["supported"] is True
        assert compliance["sus"]["version"]["id"] == 4
        assert compliance["sus"]["version"]["pretty"] == "v4"

    def test_sus_version_calculation(self) -> None:
        """Test SUS version is XSI issue minus 3."""
        compliance = {
            "posix": {},
            "sus": {},
            "xsi": {"supported": True, "version": {"issue": 8.0}},
        }

        _determine_compliance_levels(compliance, True, True, True)

        assert compliance["sus"]["version"]["id"] == 5
        assert compliance["sus"]["version"]["pretty"] == "v5"

    def test_no_sus_without_xsi(self) -> None:
        """Test SUS unsupported without XSI even with full POSIX."""
        compliance = {
            "posix": {},
            "sus": {},
            "xsi": {"supported": False},
        }

        _determine_compliance_levels(compliance, True, True, False)

        assert compliance["posix"]["supported"] is True
        assert compliance["sus"]["supported"] is False

    def test_no_sus_with_partial_posix(self) -> None:
        """Test SUS unsupported with partial POSIX even with XSI."""
        compliance = {
            "posix": {},
            "sus": {},
            "xsi": {"supported": True, "version": {"issue": 7.0}},
        }

        _determine_compliance_levels(compliance, True, False, True)

        assert compliance["posix"]["supported"] == "partial"
        assert compliance["sus"]["supported"] is False


class TestBuildCommandInventory:
    """Tests for _build_command_inventory function."""

    def test_builds_paths_dict(self) -> None:
        """Test building paths dictionary from command lookups."""
        xcu_cmds = {
            "cat": "/bin/cat",
            "grep": "/usr/bin/grep",
            "sh": "/bin/sh",
        }
        xsi_cmds = {"getconf": "/usr/bin/getconf"}

        shells, paths, missing = _build_command_inventory(xcu_cmds, xsi_cmds)

        assert "/bin/cat" in paths
        assert "/usr/bin/grep" in paths
        assert "/usr/bin/getconf" in paths
        assert missing == []

    def test_identifies_builtins(self) -> None:
        """Test identifying shell builtins (path == command name)."""
        xcu_cmds = {
            "sh": "/bin/sh",
            "command": "command",
            "test": "test",
            "[": "[",
        }
        xsi_cmds = {}

        shells, paths, missing = _build_command_inventory(xcu_cmds, xsi_cmds)

        assert "command" in shells["/bin/sh"]["builtins"]
        assert "test" in shells["/bin/sh"]["builtins"]
        assert "[" in shells["/bin/sh"]["builtins"]

    def test_collects_missing_commands(self) -> None:
        """Test collecting missing commands."""
        xcu_cmds = {"cat": "/bin/cat", "missing1": None, "sh": "/bin/sh"}
        xsi_cmds = {"missing2": None}

        shells, paths, missing = _build_command_inventory(xcu_cmds, xsi_cmds)

        assert "missing1" in missing
        assert "missing2" in missing
        assert len(missing) == 2

    def test_shell_keyed_by_sh_path(self) -> None:
        """Test shells dict is keyed by the sh command path."""
        xcu_cmds = {"sh": "/usr/local/bin/sh"}
        xsi_cmds = {}

        shells, paths, missing = _build_command_inventory(xcu_cmds, xsi_cmds)

        assert "/usr/local/bin/sh" in shells


class TestProcessComplianceCommandsResult:
    """Tests for process_compliance_commands_result function."""

    @pytest.fixture
    def mock_process_all(self):
        """Fixture to mock process_all_command_results."""
        with patch(
            "ansible_collections.o0_o.posix.plugins.module_utils."
            "compliance_utils.process_all_command_results"
        ) as mock:
            yield mock

    def test_initializes_compliance_with_metadata(
        self, mock_process_all
    ) -> None:
        """Test compliance dict initialized with standard metadata."""
        mock_process_all.return_value = (
            {
                "posix_lookup_xcu_commands": {"sh": "/bin/sh", "cat": "/bin/cat"},
                "posix_lookup_xsi_commands": {"getconf": None},
                "posix_xsh_version": None,
                "posix_xopen_support": None,
                "posix_xopen_version": None,
                "posix_xcu_version": None,
            },
            {
                "posix_lookup_xcu_commands": None,
                "posix_lookup_xsi_commands": None,
                "posix_xsh_version": None,
                "posix_xopen_support": None,
                "posix_xopen_version": None,
                "posix_xcu_version": None,
            },
        )

        result, errors = process_compliance_commands_result({})

        assert result["compliance"]["xsh"]["abbreviation"] == "XSH"
        assert result["compliance"]["xcu"]["abbreviation"] == "XCU"
        assert result["compliance"]["xsi"]["abbreviation"] == "XSI"
        assert result["compliance"]["posix"]["abbreviation"] == "POSIX"
        assert result["compliance"]["sus"]["abbreviation"] == "SUS"

    def test_returns_shells_paths_missing(self, mock_process_all) -> None:
        """Test result includes shells, paths, and missing_commands."""
        mock_process_all.return_value = (
            {
                "posix_lookup_xcu_commands": {
                    "sh": "/bin/sh",
                    "cat": "/bin/cat",
                    "command": "command",
                },
                "posix_lookup_xsi_commands": {"getconf": None},
                "posix_xsh_version": None,
                "posix_xopen_support": None,
                "posix_xopen_version": None,
                "posix_xcu_version": None,
            },
            {
                "posix_lookup_xcu_commands": None,
                "posix_lookup_xsi_commands": None,
                "posix_xsh_version": None,
                "posix_xopen_support": None,
                "posix_xopen_version": None,
                "posix_xcu_version": None,
            },
        )

        result, errors = process_compliance_commands_result({})

        assert "shells" in result
        assert "paths" in result
        assert "missing_commands" in result
        assert "/bin/sh" in result["shells"]
        assert "command" in result["shells"]["/bin/sh"]["builtins"]
        assert "getconf" in result["missing_commands"]

    def test_skips_getconf_when_not_available(self, mock_process_all) -> None:
        """Test getconf processing skipped when getconf not found."""
        mock_process_all.return_value = (
            {
                "posix_lookup_xcu_commands": {"sh": "/bin/sh"},
                "posix_lookup_xsi_commands": {"getconf": None},
                "posix_xsh_version": {"xsh": {"supported": True}},
                "posix_xopen_support": None,
                "posix_xopen_version": None,
                "posix_xcu_version": None,
            },
            {
                "posix_lookup_xcu_commands": None,
                "posix_lookup_xsi_commands": None,
                "posix_xsh_version": None,
                "posix_xopen_support": None,
                "posix_xopen_version": None,
                "posix_xcu_version": None,
            },
        )

        result, errors = process_compliance_commands_result({})

        # XSH should not be marked as supported since getconf wasn't available
        assert (
            result["compliance"]["xsh"].get("supported") is None
            or result["compliance"]["xsh"].get("supported") is False
        )

    def test_processes_getconf_when_available(self, mock_process_all) -> None:
        """Test getconf results processed when getconf is available."""
        mock_process_all.return_value = (
            {
                "posix_lookup_xcu_commands": {"sh": "/bin/sh"},
                "posix_lookup_xsi_commands": {"getconf": "/usr/bin/getconf"},
                "posix_xsh_version": {
                    "xsh": {
                        "supported": True,
                        "version": {"id": "2008", "name": "POSIX.1-2008"},
                    }
                },
                "posix_xopen_support": {"xsi": {"supported": True}},
                "posix_xopen_version": None,
                "posix_xcu_version": {
                    "xcu": {
                        "supported": True,
                        "version": {"id": "2008", "name": "POSIX.1-2008"},
                    }
                },
            },
            {
                "posix_lookup_xcu_commands": None,
                "posix_lookup_xsi_commands": None,
                "posix_xsh_version": None,
                "posix_xopen_support": None,
                "posix_xopen_version": None,
                "posix_xcu_version": None,
            },
        )

        result, errors = process_compliance_commands_result({})

        assert result["compliance"]["xsh"]["supported"] is True
        assert result["compliance"]["xcu"]["supported"] is True

    def test_collects_lookup_errors(self, mock_process_all) -> None:
        """Test errors from command lookup are collected."""
        lookup_error = ValueError("Test lookup error")
        mock_process_all.return_value = (
            {
                "posix_lookup_xcu_commands": {"sh": "/bin/sh"},
                "posix_lookup_xsi_commands": {"getconf": None},
                "posix_xsh_version": None,
                "posix_xopen_support": None,
                "posix_xopen_version": None,
                "posix_xcu_version": None,
            },
            {
                "posix_lookup_xcu_commands": [lookup_error],
                "posix_lookup_xsi_commands": None,
                "posix_xsh_version": None,
                "posix_xopen_support": None,
                "posix_xopen_version": None,
                "posix_xcu_version": None,
            },
        )

        result, errors = process_compliance_commands_result({})

        assert lookup_error in errors
