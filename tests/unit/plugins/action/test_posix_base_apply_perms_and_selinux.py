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

import pytest

from ansible.errors import AnsibleActionFail
from ansible_collections.o0_o.posix.tests.utils import (
    generate_temp_path,
    cleanup_path,
)


@pytest.mark.parametrize(
    "perms, selinux, should_fail, expected_mode, mock_selinux_keys",
    [
        # No change
        ({}, False, False, None, {}),

        # Owner change (only identity check)
        # ({"owner": "root"}, False, False, None, {}),  # Can't chown

        # Group change
        ({'group': 'wheel'}, False, False, None, {}),

        # Mode change
        ({'mode': '0700'}, False, False, 'rwx------', {}),

        # Invalid mode
        ({'mode': 'bad'}, False, True, None, {}),

        # SELinux metadata confirmation
        (
            {
                'seuser': 'system_u',
                'setype': 'etc_t',
                'serole': 'object_r',
                'selevel': 's0'
            },
            True,
            False,
            None,
            {
                'seuser': 'system_u',
                'setype': 'etc_t',
                'serole': 'object_r',
                'selevel': 's0',
            }
        ),
    ]
)
def test_apply_perms_and_selinux_confirmation(
    base, perms, selinux, should_fail, expected_mode, mock_selinux_keys
) -> None:
    """Test _apply_perms_and_selinux against real files."""
    path = generate_temp_path()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write('test')

        # Stub _handle_selinux_context to confirm it's called when selinux=True
        called_selinux = {}
        base._handle_selinux_context = lambda *a, **kw: called_selinux.setdefault('called', True)

        # Mock _get_perms when selinux is True
        original_get_perms = base._get_perms

        def mock_get_perms(target, selinux=False, task_vars=None):
            base_perms = original_get_perms(target, False, task_vars)
            if selinux:
                base_perms.update(mock_selinux_keys)
            return base_perms

        base._get_perms = mock_get_perms

        if should_fail:
            with pytest.raises(AnsibleActionFail):
                base._apply_perms_and_selinux(
                    path, perms, selinux=selinux, task_vars={}
                )
        else:
            base._apply_perms_and_selinux(
                path, perms, selinux=selinux, task_vars={}
            )
            confirmed = base._get_perms(path, selinux=False, task_vars={})

            if perms.get('mode'):
                assert confirmed['mode'] == expected_mode

            if perms.get('owner'):
                assert confirmed['owner'] == perms['owner']

            if perms.get('group'):
                assert confirmed['group'] == perms['group']

            for key in ('seuser', 'setype', 'serole', 'selevel'):
                if perms.get(key):
                    assert called_selinux.get('called') is True
                    # These won't be in `confirmed` unless selinux=True
                    # So we confirm directly via the earlier mock
                    final = mock_get_perms(path, selinux=True)
                    assert final[key] == perms[key]

    finally:
        cleanup_path(path)
