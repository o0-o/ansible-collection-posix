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
name: homes
short_description: Where each user lives, and whether it is there
version_added: "2.0.0"
description:
  - Join the C(o0_users) fact against the C(o0_paths) store and answer,
    for each user, the home their passwd entry names and what the
    store knows about that path - without running anything on the
    host.
  - A home is a path, so it is an entry of C(o0_paths) rather than a
    namespace of its own, tagged C(home) and carrying C(residents),
    the UIDs that call it home. This lookup is the audit view of
    that - it reads the users back against the store, which no single
    fact does.
  - The answer is four-state, and the first three are the collection's
    absence contract read off the C(entry) key. It is B(present) where
    the store describes the home, and C(entry) is what it observed. It
    is B(dangling) where the store holds C(null) at the path - the
    home was asked about and is not there - and C(entry) is C(null)
    with it. It is B(unknown) where the store has nothing at the path,
    and the answer carries no C(entry) key at all.
  - A dangling home is what this lookup exists to surface, and a home
    nobody gathered is not one. The two are never spelled the same
    way - C(entry) absent is "cannot say", C(entry) null is "not
    there" - so an audit that treats an ungathered store as a clean
    bill of health has to say so on purpose.
  - The fourth state is B(unnamed), where the passwd entry names no
    home a store could key - an empty sixth field, or a relative path,
    which names nothing on its own. That is a fact about the user
    rather than an absence in the store, so it carries neither
    C(entry) nor C(path).
options:
  _terms:
    description:
      - Users to answer for, by UID (int) or username (str).
      - With no terms, every user in C(o0_users) is answered for, in
        order of UID. That is the audit view.
      - A term naming no user is an error, because the question is
        about a user and a name that is not one asks about nothing.
    type: list
    elements: raw
  host:
    description:
      - Read C(o0_users) and C(o0_paths) from another host's variables
        rather than the current host's.
      - A host that has not gathered the facts has no users to answer
        for, so a call with no terms answers with nothing at all.
    type: str
notes:
  - This lookup reads the C(o0_users) and C(o0_paths) facts from the
    variable namespace and runs nothing on the host. Gather them
    first; a namespace holding no C(o0_paths) was never asked about
    any path, so every user answers B(unknown).
  - The lookup does fail when C(o0_users) or C(o0_paths) is present
    but is not a dictionary, when an C(o0_paths) entry is neither null
    nor a mapping, and when a term names no user.
  - The home a user names is keyed the way the store keys it, so a
    trailing slash or a C(.) component in a passwd entry still finds
    the path it names. C(path) carries that key and C(home) carries
    the field as it was written, which are not always the same string.
  - Two users sharing a home get one answer each, both naming the one
    path. Where a home is a symlink, the store also holds the target,
    carrying the same residents; this lookup answers for the home the
    passwd entry names, and C(entry.target) leads to the rest.
seealso:
  - module: o0_o.posix.facts
    description: Gather POSIX facts, C(o0_paths) among them
  - module: o0_o.posix.users
    description: Gather POSIX user and group information
  - plugin: o0_o.posix.user
    plugin_type: lookup
    description: Look up user information by UID or username
  - plugin: o0_o.posix.commands
    plugin_type: lookup
    description: Resolve command names against a POSIX search path
"""

EXAMPLES = r"""
- name: Gather the facts the lookup reads
  o0_o.posix.facts:
    gather_subset: ['users']

- name: Audit every user's home at once
  ansible.builtin.debug:
    msg: "{{ lookup('o0_o.posix.homes', wantlist=True) }}"

- name: Name the users whose home is not there
  ansible.builtin.debug:
    msg: >-
      {{ dangling | map(attribute='name') | list }}
  vars:
    dangling: >-
      {{ lookup('o0_o.posix.homes', wantlist=True)
         | selectattr('state', 'equalto', 'dangling') | list }}

- name: Fail the play on a home the host was asked about and lacks
  ansible.builtin.assert:
    that:
      - answers | selectattr('state', 'equalto', 'dangling')
        | list | length == 0
    fail_msg: >-
      Users are missing the home they log into:
      {{ answers | selectattr('state', 'equalto', 'dangling')
         | map(attribute='home') | list }}
  vars:
    answers: "{{ lookup('o0_o.posix.homes', wantlist=True) }}"

- name: Refuse to call an ungathered store a clean audit
  ansible.builtin.assert:
    that:
      - answers | selectattr('state', 'equalto', 'unknown')
        | list | length == 0
    fail_msg: >-
      Nothing gathered says whether these homes exist:
      {{ answers | selectattr('state', 'equalto', 'unknown')
         | map(attribute='home') | list }}
  vars:
    answers: "{{ lookup('o0_o.posix.homes', wantlist=True) }}"

- name: Answer for one user by name
  ansible.builtin.debug:
    msg: "{{ lookup('o0_o.posix.homes', 'o0-o') }}"

- name: Answer for several users by UID
  ansible.builtin.debug:
    msg: "{{ lookup('o0_o.posix.homes', 0, 1000, wantlist=True) }}"

- name: Read the owner of a home the store described
  ansible.builtin.debug:
    msg: "{{ answer['entry']['uid'] }}"
  vars:
    answer: "{{ lookup('o0_o.posix.homes', 'o0-o') }}"
  when: answer['state'] == 'present'

- name: Audit another host's homes from this play
  ansible.builtin.debug:
    msg: "{{ lookup('o0_o.posix.homes', host='webserver1', wantlist=True) }}"
"""

RETURN = r"""
_raw:
  description:
    - One answer per user asked about, in the order asked, or one per
      user in C(o0_users) in order of UID where no user was named.
    - The state reads off the C(entry) key, following the collection's
      absence contract. A mapping is what the store observed of the
      home; C(null) is a home confirmed not to exist; and no C(entry)
      key at all is a home the store was never asked about.
    - A B(dangling) answer is a home the host was asked about and does
      not have. An B(unknown) answer is not one, and never carries an
      C(entry) key to be mistaken for one.
  type: list
  elements: dict
  contains:
    uid:
      description: The UID of the user the answer is about.
      returned: always
      type: int
      sample: 1000
    name:
      description:
        - The username, as C(o0_users) carries it. C(null) where the
          entry has no name.
      returned: always
      type: str
      sample: o0-o
    home:
      description:
        - The home the passwd entry names, as it was written. C(null)
          where it names none.
      returned: always
      type: str
      sample: /home/o0-o
    state:
      description:
        - C(present) where the store describes the home, C(dangling)
          where the store holds it as not existing, C(unknown) where
          the store has nothing at the path, and C(unnamed) where the
          user names no home a store could key.
      returned: always
      type: str
      choices:
        - present
        - dangling
        - unknown
        - unnamed
      sample: present
    path:
      description:
        - The home in the form C(o0_paths) keys it by, which is what
          the answer was read at.
        - Absent from the answer where the state is C(unnamed).
      returned: when the state is not C(unnamed)
      type: str
      sample: /home/o0-o
    entry:
      description:
        - What the store observed about the home - its metadata, the
          C(home) tag, and C(residents), the UIDs that call it home -
          or C(null) where the home does not exist.
        - Absent from the answer where the state is C(unknown) or
          C(unnamed).
      returned: when the state is C(present) or C(dangling)
      type: dict
      sample:
        type: directory
        uid: 1000
        gid: 20
        tags:
          - posix
          - home
        residents:
          - 1000
  sample:
    - uid: 0
      name: root
      home: /var/root
      state: present
      path: /var/root
      entry:
        type: directory
        uid: 0
        gid: 0
        tags:
          - posix
          - home
        residents:
          - 0
    - uid: 1000
      name: o0-o
      home: /home/o0-o
      state: dangling
      path: /home/o0-o
      entry: null
    - uid: 1001
      name: ghost
      home: /home/ghost
      state: unknown
      path: /home/ghost
"""

from typing import Any, Optional

from ansible.errors import AnsibleLookupError
from ansible.plugins.lookup import LookupBase

from ansible_collections.o0_o.utils.plugins.module_utils import (
    VarsLookupBase,
)
from ansible_collections.o0_o.posix.plugins.module_utils import (
    canonicalize,
    lookup_user,
)

# The four answers a user's home can get. The first three are the
# absence contract in a word - an entry observed, a null gathered, or
# a path never asked about; the fourth is a user who named no path.
PRESENT = "present"
DANGLING = "dangling"
UNKNOWN = "unknown"
UNNAMED = "unnamed"


class LookupModule(LookupBase, VarsLookupBase):
    """Answer where each user lives, and whether it is there."""

    def run(
        self,
        terms: list[Any],
        variables: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Perform the lookup.

        :param list terms: Users to answer for, by UID or username;
            none for every user there is
        :param dict variables: Available Ansible variables
        :returns list: One answer per user, in order
        :raises AnsibleLookupError: If a fact is not the shape it has
            to be, or a term names no user
        """
        users = self.lookup_var("o0_users", default={}, **kwargs)

        if not isinstance(users, dict):
            raise AnsibleLookupError(
                f"'o0_users' fact is not a dictionary, got "
                f"{type(users).__name__}"
            )

        # The store the homes are answered from. The default makes an
        # absent fact a store that was never asked anything, so every
        # home answers unknown
        paths = self.lookup_var("o0_paths", default={}, **kwargs)

        if not isinstance(paths, dict):
            raise AnsibleLookupError(
                f"'o0_paths' fact is not a dictionary, got "
                f"{type(paths).__name__}"
            )

        if not terms:
            return [self._answer(entry, paths) for entry in self._every(users)]

        ret = []
        for term in terms:
            # Template the term to resolve any Jinja2 expressions
            term = self._templar.template(term)

            ret.append(self._answer(self._user(term, users), paths))

        return ret

    @staticmethod
    def _every(users: dict[str, Any]) -> list[dict[str, Any]]:
        """Every user the fact holds, in order of UID.

        The fact is keyed by the stringified UID, so ordering on the
        key is ordering on text; the audit reads in numeric order,
        which is the order a passwd file is usually read in.  An entry
        that is not a mapping is not a user and is passed over.

        :param dict[str, Any] users: The o0_users mapping
        :returns list[dict[str, Any]]: The user entries, in UID order
        """
        entries = [
            entry for entry in users.values() if isinstance(entry, dict)
        ]

        def uid(entry: dict[str, Any]) -> tuple[int, int]:
            """Sort key putting an entry with no UID last."""
            value = entry.get("uid")
            if isinstance(value, int) and not isinstance(value, bool):
                return (0, value)
            return (1, 0)

        return sorted(entries, key=uid)

    def _user(self, term: Any, users: dict[str, Any]) -> dict[str, Any]:
        """Resolve one term to the user it names.

        :param Any term: A UID (int) or a username (str)
        :param dict[str, Any] users: The o0_users mapping
        :returns dict[str, Any]: The user entry
        :raises AnsibleLookupError: If the term names no user
        """
        if isinstance(term, bool) or not isinstance(term, (int, str)):
            raise AnsibleLookupError(
                f"A term must be a UID or a username, got"
                f" {type(term).__name__}: {term!r}"
            )

        entry = lookup_user(term, users)

        if entry is not None:
            return entry

        if not users:
            raise AnsibleLookupError(
                f"No user {term!r} to answer for: no 'o0_users' fact was"
                f" gathered, so this host has no users to read a home"
                f" against. Gather the users subset first"
            )

        raise AnsibleLookupError(
            f"No user {term!r} in the 'o0_users' fact, so there is no"
            f" home to answer about"
        )

    def _answer(
        self, user: dict[str, Any], paths: dict[str, Any]
    ) -> dict[str, Any]:
        """Answer for one user's home from the store, in four states.

        A home the store describes is present, a home it holds as null
        is dangling, and a home it has nothing at was never asked
        about.  The fourth answer is not the store's: a passwd entry
        naming no home, or naming something no store could key, has no
        path to ask about in the first place.

        :param dict[str, Any] user: One o0_users entry
        :param dict[str, Any] paths: The o0_paths store
        :returns dict[str, Any]: The answer, keyed uid, name, home,
            state, path and entry
        :raises AnsibleLookupError: If the store's entry for the home
            is neither null nor a mapping of observed facts
        """
        uid = user.get("uid")
        name = user.get("name")
        home = user.get("home")

        answer: dict[str, Any] = {
            "uid": uid if isinstance(uid, int) else None,
            "name": name if isinstance(name, str) else None,
            "home": home if isinstance(home, str) and home else None,
        }

        if answer["home"] is None or not home.startswith("/"):
            # A relative sixth field names a directory only in
            # relation to a working directory, which a passwd entry
            # has none of, so it names no home rather than one
            # somewhere under wherever the shell started
            answer["state"] = UNNAMED
            return answer

        path = canonicalize(home)
        answer["state"] = UNKNOWN
        answer["path"] = path

        if path not in paths:
            return answer

        entry = paths[path]

        if entry is None:
            answer["state"] = DANGLING
            answer["entry"] = None
            return answer

        if not isinstance(entry, dict):
            raise AnsibleLookupError(
                f"The 'o0_paths' entry for {path!r} is neither null nor"
                f" a mapping of observed facts, got"
                f" {type(entry).__name__}: {entry!r}"
            )

        answer["state"] = PRESENT
        answer["entry"] = dict(entry)

        return answer
