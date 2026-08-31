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

DOCUMENTATION = r"""
---
module: users
short_description: Gather POSIX user and group information
version_added: "2.0.0"
description:
  - Collects user and group information from C(/etc/passwd) and
    C(/etc/group) on POSIX hosts, overlaid with the host's own
    resolved view of those users where the host has a C(getent) to
    ask.
  - Returns the canonical C(o0_users) and C(o0_groups) mappings, keyed
    by stringified UID and GID and cross-referenced by numeric ID.
    The C(o0_o.posix.facts) module publishes the same shape under the
    same names, along with the C(o0_paths) entries for the homes users
    live in, the shells they log in with, and the login shells file.
  - Every entry names where it came from in C(evidence) - the paths
    that were read and the commands that were run, named concretely -
    so a consumer reads provenance rather than guessing at it. That is
    the one provenance vocabulary this collection speaks, and the
    C(evidence) notes below document its kinds.
options:
  passwd_path:
    description:
      - Path to the C(/etc/passwd) file.
    type: str
    default: /etc/passwd
  group_path:
    description:
      - Path to the C(/etc/group) file.
    type: str
    default: /etc/group
  shells_path:
    description:
      - Path to the C(/etc/shells) file.
      - A host that does not have this file leaves the path out of
        C(o0_paths) rather than filing it as a file that names no
        login shells.
    type: str
    default: /etc/shells
extends_documentation_fragment:
  - o0_o.posix.evidence
author:
  - oØ.o (@o0-o)
notes:
  - This module is implemented as an action plugin and supports raw
    fallback.
  - Group membership is reported in numeric IDs on both sides - a
    user's C(groups) lists GIDs and a group's C(members) lists UIDs -
    and every user counts as a member of their primary group.
  - The flat files are the base of the composition and C(getent) is an
    overlay on it. A host with no C(getent) - macOS has none, and
    C(o0_o.posix) does not speak Darwin's Directory Services - is
    gathered from its files alone. That is a correct gather, not a
    degraded one, and C(evidence) states it rather than leaving it to
    be inferred.
  - Where C(getent) is present, what it enumerates is what the host's
    name service switch resolves, which is not always everything it
    can resolve. An SSSD-backed host disables enumeration by default,
    so its directory users may be absent from C(o0_users) even though
    the host resolves them by name. C(evidence) is what keeps that
    honest - it names what answered, not what exists.
  - A C(getent) is believed only once it has behaved like one.
    Something answering to the name may be a shell function that greps
    the flat files with no idea the name service switch exists, so the
    module asks for an enumeration and believes the answer only if it
    got one. A candidate that fails that is treated as absent, which
    is never an error. C(getent -V) is not consulted - it is a glibc
    marker rather than a getent one, and musl's real C(getent) rejects
    it.
  - Whether a user's shell is a known login shell is not stored. The
    login shells C(/etc/shells) names are the C(config) of that path
    in C(o0_paths), and the C(o0_o.posix.shells) lookup surfaces them,
    so C(user.shell in lookup('o0_o.posix.shells').shells) answers the
    question wherever it is asked and leaves no copy to go stale. The
    lookup is worth going through rather than reading the store
    directly, because it tells a host that names no login shells from
    one nothing ever asked.
  - The module does not read SSH keys. A key is a fact about SSH, and
    the collection that knows what one means is where it is gathered.
seealso:
  - plugin: o0_o.posix.homes
    plugin_type: lookup
    description: Where each user lives, and whether it is there
  - plugin: o0_o.posix.shells
    plugin_type: lookup
    description: The login shells a host names
  - ref: o0_o.posix.id filter <ansible_collections.o0_o.posix.id_filter>
    description: Parse id command output
  - ref: o0_o.posix.group filter <ansible_collections.o0_o.posix.group_filter>
    description: Parse /etc/group content
  - ref: >-
      o0_o.posix.passwd filter
      <ansible_collections.o0_o.posix.passwd_filter>
    description: Parse /etc/passwd content
"""

EXAMPLES = r"""
- name: Gather user and group information
  o0_o.posix.users:
  register: system_users

- name: Expose the canonical facts for the user and group lookups
  ansible.builtin.set_fact:
    o0_users: "{{ system_users['o0_users'] }}"
    o0_groups: "{{ system_users['o0_groups'] }}"

- name: Name the users who log in with a shell the host names
  ansible.builtin.debug:
    msg: "{{ item.value.name }}"
  loop: "{{ system_users['o0_users'] | dict2items }}"
  when: item.value.shell in lookup('o0_o.posix.shells').shells

- name: List the members of a group by GID
  ansible.builtin.debug:
    msg: "{{ system_users['o0_groups']['20']['members'] }}"
"""

RETURN = r"""
o0_users:
  description: Mapping of users keyed by stringified UID
  returned: always
  type: dict
  contains:
    name:
      description: Username
      type: str
      sample: o0-o
    uid:
      description: Numeric user ID
      type: int
      sample: 1000
    gid:
      description: Numeric ID of the user's primary group
      type: int
      sample: 20
    gecos:
      description: User comment/info field
      type: str
      sample: 'User Account'
    home:
      description: Home directory path
      type: str
      sample: /home/o0-o
    shell:
      description: Login shell
      type: str
      sample: /bin/bash
    groups:
      description: >-
        GIDs of every group the user belongs to, primary group
        included
      type: list
      elements: int
      sample: [20, 101]
    evidence:
      description:
        - The concrete origins the entry's own record came from, by
          kind, base first within each kind. This is the collection's
          one provenance vocabulary, documented in full by the
          C(evidence) notes on this module.
        - C(files) names the paths that were read. Each is a key of
          C(o0_paths), so an entry joins against the file it came out
          of.
        - C(commands) names the enumerations that were consulted, by
          the name each is known by rather than by the argv it was run
          with. The name says what was consulted, which is what a
          consumer has to know; what it said is the entry itself.
        - Both kinds are always present, because both are always
          attempted. A kind that contributed nothing to the entry is
          empty rather than absent, so a host with no C(getent)
          names no command rather than leaving the field off. At least
          one origin is named across the two. The vocabulary's third
          kind, C(config), is absent, because no user or group record
          is composed from a configuration variable.
      type: dict
      contains:
        files:
          description: The paths that were read, as C(o0_paths) keys
          type: list
          elements: str
          sample: ["/etc/passwd"]
        commands:
          description: >-
            The commands that were consulted, by the name each is
            known by
          type: list
          elements: str
          sample: ["getent"]
      sample:
        files:
          - /etc/passwd
        commands:
          - getent
o0_groups:
  description: >-
    Mapping of groups keyed by stringified GID. Each entry includes the
    group name when available, the GID, the UIDs of every member, and
    the origins the group's own record came from, in the same shape
    C(o0_users) names them. Membership does not enter into
    C(evidence) - a group's evidence is where its record came from,
    not where its members' did - except for a group no group source
    named at all,
    which exists only because a passwd entry claimed it as a primary
    and so carries the origins of the users claiming it, the passwd
    file and the passwd enumeration rather than the group ones.
  returned: always
  type: dict
  sample:
    "20":
      name: staff
      gid: 20
      members:
        - 0
        - 1000
      evidence:
        files:
          - /etc/group
        commands:
          - getent
o0_shells:
  description:
    - The login shells the host names, keyed by shell path, which is
      what makes C(user.shell in o0_shells) a question a host can
      answer. The same answer C(o0_paths['/etc/shells']['config'])
      lists, keyed rather than ordered.
    - Each key carries C(binary), the file the name finally resolves
      to, copied from the chain C(o0_paths) already walked, and
      nothing else - M(o0_o.posix.facts) files what running each shell
      out of a home produced, under C(homes). This module names the shells and
      runs none of them, because what a shell's configuration does is
      only knowable by running it.
  returned: when the host names its login shells
  type: dict
  sample:
    /bin/sh:
      binary: /usr/bin/bash
    /bin/zsh:
      binary: /bin/zsh
o0_paths:
  description:
    - What the module observed about the paths it read, keyed by the
      canonical absolute path. The store is flat - a path is a key of
      its own and nothing about a path is filed under another path.
    - The homes users live in are entries here, carrying what a read
      of that path said and nothing about who lives there. Two users
      sharing a home share one entry, and every step a home resolves
      through gets an entry of its own, because that is where their
      files are. Who calls a path home is the join between C(o0_users)
      and this store, which the C(o0_o.posix.homes) lookup makes from
      the field C(o0_users) already carries.
    - A home the module read and found is not there is C(null), a
      dangling home, which the C(o0_o.posix.homes) lookup surfaces by
      reading C(o0_users) back against this store. A home no read
      reached is left out entirely, because a store reports what it
      asked rather than what it assumed.
    - The login shells are entries here too, with the file metadata of
      the shell itself. Two reasons put one here and either is enough -
      a passwd entry holds it, or I(shells_path) names it - and reading
      only what users hold would leave out C(/bin/sh) on any host
      where no passwd entry names it, which is most of them.
    - An entry describes the path it is keyed by, so a shell that is a
      link reports a C(type) of C(link) and the C(target) the listing
      gave
      rather than its target's metadata. Every step the shell resolves
      through gets an entry of its own, so a C(/bin/sh) that is a link
      to C(bash) puts C(bash) in the store beside it and
      C(resolution) says how the one reached the other.
    - A single file parsed on its own lands at its own path - the
      bytes under C(content), the meaning parsed out of them under
      C(config) - so the login shells the host names are
      C(o0_paths[shells_path]['config']), surfaced by the
      C(o0_o.posix.shells) lookup. That is a different claim from the
      shells users hold - the file lists what the host is willing to
      call a login shell, whether anyone holds it or not. A host whose
      shells file could not be read leaves that path out rather than
      filing it as a file that names none, which is why the lookup
      answers unknown there rather than empty.
  returned: when the module observed a path
  type: dict
  contains:
    evidence:
      description: >-
        What was consulted about this path, in the collection's one
        provenance vocabulary. Provenance sits on the entry because it
        varies by entry - a home was described by a metadata read and
        the shells file by the C(cat) that read it. A file's own entry
        names the command that read it and no path, because the file
        is the fact rather than evidence for itself.
      type: dict
      sample:
        commands:
          - ls
          - sh
          - stat
    origins:
      description: >-
        The modules that composed the entry, by FQCN, sorted. It
        travels with C(evidence) - one says what was consulted, the
        other who consulted it - and both accumulate where every other
        field is replaced, so a path two producers described names
        both of them. See the C(evidence) notes.
      type: list
      elements: str
      sample:
        - o0_o.posix.read
        - o0_o.posix.users
    resolution:
      description: >-
        The chain the path resolves through, an ordered list of the
        absolute paths the walk visited, from the path itself to the
        canonical path it names. Every step has an entry of its own in
        this store.
      type: list
      elements: str
    content:
      description: The bytes read from the path
      type: str
    config:
      description: >-
        The meaning parsed out of the file - for C(/etc/shells), the
        login shells it names, in the order it names them
      type: raw
  sample:
    /home/o0-o:
      type: directory
      uid: 1000
      gid: 20
      origins:
        - o0_o.posix.read
        - o0_o.posix.users
    /etc/shells:
      content: "/bin/sh\n/bin/zsh\n"
      config:
        - /bin/sh
        - /bin/zsh
"""
from ansible.module_utils.basic import AnsibleModule


def main() -> None:
    """Fail if this module is run directly without the action plugin."""

    argument_spec = {
        "passwd_path": {
            "type": "str",
            "default": "/etc/passwd",
            "no_log": False,
        },
        "group_path": {"type": "str", "default": "/etc/group"},
        "shells_path": {"type": "str", "default": "/etc/shells"},
    }

    module = AnsibleModule(
        argument_spec=argument_spec, supports_check_mode=True
    )
    module.fail_json(msg="This module must be run via its action plugin.")


if __name__ == "__main__":
    main()
