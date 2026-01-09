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

"""Unit tests for compliance action plugin."""

from __future__ import annotations

import pytest

try:
    from ansible_collections.o0_o.posix.plugins.action.compliance import (
        ActionModule,
    )
except ModuleNotFoundError:  # pragma: no cover - ansible missing in tests
    ActionModule = None  # type: ignore

pytestmark = pytest.mark.skipif(
    ActionModule is None, reason="ansible package is required"
)


class DummyComplianceAction(ActionModule):
    """Minimal ActionModule subclass for testing helper methods."""

    def __init__(self) -> None:
        # Skip parent __init__ which requires Ansible internals
        pass


class TestFormatComplianceMessage:
    """Tests for _format_compliance_message method."""

    @pytest.fixture
    def action(self) -> DummyComplianceAction:
        """Create a DummyComplianceAction instance for testing."""
        return DummyComplianceAction()

    def test_sus_compliant_with_version(self, action) -> None:
        """Test message for SUS-compliant system with version."""
        result = {
            "compliance": {
                "sus": {"supported": True, "version": {"pretty": "v4"}},
                "posix": {"supported": True},
            }
        }

        msg = action._format_compliance_message(result)

        assert msg == "System is SUS-compliant (v4)"

    def test_sus_compliant_without_version(self, action) -> None:
        """Test message for SUS-compliant system without version info."""
        result = {
            "compliance": {
                "sus": {"supported": True},
                "posix": {"supported": True},
            }
        }

        msg = action._format_compliance_message(result)

        assert msg == "System is SUS-compliant"

    def test_posix_compliant_all_components(self, action) -> None:
        """Test message for POSIX-compliant system with all components."""
        result = {
            "compliance": {
                "sus": {"supported": False},
                "posix": {"supported": True},
                "xsh": {"supported": True},
                "xcu": {"supported": True},
                "xsi": {"supported": True},
            }
        }

        msg = action._format_compliance_message(result)

        assert msg == "System is POSIX-compliant (XSH, XCU, XSI)"

    def test_posix_compliant_xsh_xcu_only(self, action) -> None:
        """Test message for POSIX-compliant without XSI."""
        result = {
            "compliance": {
                "sus": {"supported": False},
                "posix": {"supported": True},
                "xsh": {"supported": True},
                "xcu": {"supported": True},
                "xsi": {"supported": False},
            }
        }

        msg = action._format_compliance_message(result)

        assert msg == "System is POSIX-compliant (XSH, XCU)"

    def test_posix_compliant_no_components_listed(self, action) -> None:
        """Test message when POSIX supported but no component details."""
        result = {
            "compliance": {
                "sus": {"supported": False},
                "posix": {"supported": True},
                "xsh": {},
                "xcu": {},
                "xsi": {},
            }
        }

        msg = action._format_compliance_message(result)

        assert msg == "System is POSIX-compliant"

    def test_partial_posix_xsh_only(self, action) -> None:
        """Test message for partial POSIX with XSH only."""
        result = {
            "compliance": {
                "sus": {"supported": False},
                "posix": {"supported": "partial"},
                "xsh": {"supported": True},
                "xcu": {"supported": False},
            }
        }

        msg = action._format_compliance_message(result)

        assert msg == "System is partially POSIX-compliant (XSH)"

    def test_partial_posix_xcu_only(self, action) -> None:
        """Test message for partial POSIX with XCU only."""
        result = {
            "compliance": {
                "sus": {"supported": False},
                "posix": {"supported": "partial"},
                "xsh": {"supported": False},
                "xcu": {"supported": True},
            }
        }

        msg = action._format_compliance_message(result)

        assert msg == "System is partially POSIX-compliant (XCU)"

    def test_partial_posix_no_components(self, action) -> None:
        """Test message for partial POSIX without component details."""
        result = {
            "compliance": {
                "sus": {"supported": False},
                "posix": {"supported": "partial"},
                "xsh": {},
                "xcu": {},
            }
        }

        msg = action._format_compliance_message(result)

        assert msg == "System is partially POSIX-compliant"

    def test_not_posix_compliant(self, action) -> None:
        """Test message for non-POSIX-compliant system."""
        result = {
            "compliance": {
                "sus": {"supported": False},
                "posix": {"supported": False},
            }
        }

        msg = action._format_compliance_message(result)

        assert msg == "System is not POSIX-compliant"

    def test_empty_compliance(self, action) -> None:
        """Test message when compliance dict is empty."""
        result = {"compliance": {}}

        msg = action._format_compliance_message(result)

        assert msg == "System is not POSIX-compliant"

    def test_missing_compliance_key(self, action) -> None:
        """Test message when compliance key is missing."""
        result = {}

        msg = action._format_compliance_message(result)

        assert msg == "System is not POSIX-compliant"

    def test_sus_priority_over_posix(self, action) -> None:
        """Test that SUS message takes priority over POSIX message."""
        result = {
            "compliance": {
                "sus": {"supported": True, "version": {"pretty": "v4"}},
                "posix": {"supported": True},
                "xsh": {"supported": True},
                "xcu": {"supported": True},
                "xsi": {"supported": True},
            }
        }

        msg = action._format_compliance_message(result)

        # Should show SUS message, not POSIX
        assert "SUS" in msg
        assert "POSIX" not in msg
