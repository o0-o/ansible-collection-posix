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

"""Command specifications for POSIX operations.

Defines generic command specs and module-specific command specs.
Used with process_command_spec from core to build command requests.
"""

from __future__ import annotations

from ansible_collections.o0_o.core.plugins.module_utils.parsers import (
    strip_only,
)

from ansible_collections.o0_o.posix.plugins.module_utils.compliance_parsers import (  # noqa: E501
    _parse_posix_version,
    _parse_sh_test,
    _parse_xopen_support,
    _parse_xopen_version,
)
from ansible_collections.o0_o.posix.plugins.module_utils.df_utils import (
    _parse_df,
)
from ansible_collections.o0_o.posix.plugins.module_utils.dmidecode_utils import (  # noqa: E501
    _parse_dmidecode,
)
from ansible_collections.o0_o.posix.plugins.module_utils.getconf_utils import (
    GETCONF_RCS,
    _parse_getconf,
)
from ansible_collections.o0_o.posix.plugins.module_utils.getent_utils import (
    GETENT_COMMANDS,
    GETENT_RCS,
    _parse_getent,
)
from ansible_collections.o0_o.posix.plugins.module_utils.id_utils import (
    _parse_effective_uid,
)
from ansible_collections.o0_o.posix.plugins.module_utils.limits_utils import (
    LIMITS_HARD_MARKER,
    LIMITS_SOFT_MARKER,
    _parse_ulimit,
    _parse_umask,
)
from ansible_collections.o0_o.posix.plugins.module_utils.locale_utils import (
    _parse_locale,
)
from ansible_collections.o0_o.posix.plugins.module_utils.mount_utils import (
    _parse_mount,
)
from ansible_collections.o0_o.posix.plugins.module_utils.shells_utils import (
    SHELL_END_MARKER,
    SHELL_ENV_MARKER,
    SHELL_LOCALE_MARKER,
    SHELL_RCS,
    SHELL_UMASK_MARKER,
    _parse_shell_config,
)
from ansible_collections.o0_o.posix.plugins.module_utils.timezone_utils import (  # noqa: E501
    _parse_timezone,
)
from ansible_collections.o0_o.posix.plugins.module_utils.uname_utils import (
    _parse_uname,
)

# Env variable collection spec (no parser — true passthrough)
ENV_COMMAND_SPEC = {
    "posix": {
        "env_var": {
            "command": "set -eu; printf '%s' \"${{{env}}}\"",
        },
    },
}

# Reading a file's bytes. No parser: the bytes are the answer, and
# what they mean is the reader's to parse. One request per path, so a
# producer's file reads ride the batch its probes ride.
FILE_COMMAND_SPEC = {
    "posix": {
        "file": {
            "command": ("cat", "{path}"),
        },
    },
}

# The host's own resolved view of its users and groups. One
# enumeration per database, which is the probe as well as the answer:
# a getent that enumerates has proved itself one, and a candidate that
# does not has said all it is going to. Every plausible exit status is
# a non-error, so the parser rather than the runner is what decides
# whether the host has a getent worth believing.
GETENT_COMMAND_SPEC = {
    "posix": {
        "getent_passwd": {
            "command": GETENT_COMMANDS["passwd"],
            "parser": _parse_getent,
            "parser_kwargs": {"database": "passwd"},
            "non_error_codes": GETENT_RCS,
        },
        "getent_group": {
            "command": GETENT_COMMANDS["group"],
            "parser": _parse_getent,
            "parser_kwargs": {"database": "group"},
            "non_error_codes": GETENT_RCS,
        },
    },
}

# What the host says its own configuration is.  One invocation per
# variable, which is the only interface POSIX defines, and every
# plausible refusal is a non-error so the parser rather than the
# runner decides what the host knows.
GETCONF_COMMAND_SPEC = {
    "posix": {
        "getconf_sysconf": {
            "command": ("getconf", "{var}"),
            "parser": _parse_getconf,
            "non_error_codes": GETCONF_RCS,
        },
        # The same interface asked of a filesystem rather than a host.
        # The path is an argument, so a mountpoint with a space in it
        # reaches getconf whole.
        "getconf_pathconf": {
            "command": ("getconf", "{var}", "{path}"),
            "parser": _parse_getconf,
            "non_error_codes": GETCONF_RCS,
        },
    },
}

# Effective user id spec — the key the canonical user facts nest under
ID_COMMAND_SPEC = {
    "posix": {
        "effective_uid": {
            "command": ("id", "-u"),
            "parser": _parse_effective_uid,
        },
    },
}

# Generic reusable command specifications
COMMAND_SPEC = {
    "posix": {
        "lookup_command": {
            # NOTE: dash only outputs the first arg to `command -v`.
            # Use cmd as a list to generate one request per command.
            "command": ("command", "-v", "{cmd}"),
            "parser": strip_only,
        },
    },
}

# Uname command spec
UNAME_COMMAND_SPEC = {
    "posix": {
        "uname": {
            "command": ("uname", "-a"),
            "parser": _parse_uname,
        },
    },
}

# What the shell says about the process it hands you.  Both are shell
# builtins, so both are asked through a shell; the soft and hard sets
# ride the one invocation, marked apart so the parser can tell which
# it is reading.
LIMITS_COMMAND_SPEC = {
    "posix": {
        "ulimit": {
            "command": (
                "sh",
                "-c",
                f"echo {LIMITS_SOFT_MARKER}; ulimit -aS 2>/dev/null;"
                f" echo {LIMITS_HARD_MARKER}; ulimit -aH 2>/dev/null",
            ),
            "parser": _parse_ulimit,
        },
        "umask": {
            "command": ("sh", "-c", "umask"),
            "parser": _parse_umask,
        },
    },
}

# Locale command spec
LOCALE_COMMAND_SPEC = {
    "posix": {
        "locale": {
            "command": ("locale",),
            "parser": _parse_locale,
        },
    },
}

# Mount command spec. The mounts fact is composed from both
# commands: mount names the type and options, df names the capacity.
MOUNT_COMMAND_SPEC = {
    "posix": {
        "mount": {
            "command": ("mount",),
            "parser": _parse_mount,
        },
        "df": {
            "command": ("df", "-P"),
            "parser": _parse_df,
        },
    },
}

# What running a login shell out of a given home actually produces.
# env(1) is POSIX and takes its assignment as an argument rather than
# as shell syntax, so a home with a space or a quote in it reaches the
# shell whole; -l is what makes the shell read the login files, which
# is the only reason to run it at all.  The script ends in an echo so
# that a probe that ran exits 0 whatever the utilities inside it did,
# leaving 126 and 127 to mean what they mean: no such shell.
SHELL_COMMAND_SPEC = {
    "posix": {
        "shell_config": {
            "command": (
                "env",
                "HOME={home}",
                "{shell}",
                "-l",
                "-c",
                f"echo {SHELL_UMASK_MARKER}; umask;"
                f" echo {SHELL_ENV_MARKER}; env;"
                f" echo {SHELL_LOCALE_MARKER}; locale 2>/dev/null;"
                f" echo {SHELL_END_MARKER}",
            ),
            "parser": _parse_shell_config,
            "non_error_codes": SHELL_RCS,
        },
    },
}

# Timezone command spec
TIMEZONE_COMMAND_SPEC = {
    "posix": {
        "timezone": {
            "command": ("date", "+%Z %z"),
            "parser": _parse_timezone,
        },
    },
}

# Dmidecode command spec
DMIDECODE_COMMAND_SPEC = {
    "posix": {
        "dmidecode": {
            "command": ("dmidecode",),
            "parser": _parse_dmidecode,
        },
    },
}

# Compliance-specific command specs for getconf and shell tests
COMPLIANCE_COMMAND_SPEC = {
    "posix": {
        "sh_test": {
            "command": ("sh", "-c", 'x=1; [ "$x" = 1 ] && printf "posix sh"'),
            "parser": _parse_sh_test,
        },
        "xsh_version": {
            "command": ("getconf", "_POSIX_VERSION"),
            "parser": _parse_posix_version,
        },
        "xcu_version": {
            "command": ("getconf", "_POSIX2_VERSION"),
            "parser": _parse_posix_version,
        },
        "xsi_support": {
            "command": ("getconf", "_XOPEN_UNIX"),
            "parser": _parse_xopen_support,
        },
        "xsi_version": {
            "command": ("getconf", "_XOPEN_VERSION"),
            "parser": _parse_xopen_version,
        },
    },
}
