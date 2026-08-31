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
name: shells
short_description: The login shells a host names, or nothing it can say
version_added: "2.0.0"
description:
  - Answer with the login shells a host names in C(/etc/shells), read
    from the C(o0_paths) fact, without running anything on the host.
  - A single file parsed on its own lands at its own path in the
    store - the bytes under C(content), the meaning parsed out of them
    under C(config) - so the shells are
    C(o0_paths['/etc/shells']['config']). This lookup reads that, and
    keeps apart the answers a bare read of it collapses.
  - The answer is tri-state. It is B(named) where the store holds the
    parsed file, and C(shells) is what it names - an empty list where
    it names none, which is a host that has the file and lists nothing
    in it. It is B(missing) where the store holds C(null) at the path,
    the file having been asked about and found not to exist, and
    C(shells) is C(null) with it. It is B(unknown) where the store has
    no parsed answer at that path, and the answer carries no C(shells)
    key at all.
  - Those three are the collection's absence contract - a key absent
    was never asked, C(null) was asked and does not exist, a typed
    empty exists and is empty - applied to an answer rather than to a
    store.
  - A host whose shells file could not be read leaves the path out of
    the store rather than filing it as a file that names none, so it
    answers B(unknown). That is the distinction this lookup exists to
    keep - C(shells) absent is "cannot say", C(shells) empty is "names
    none" - and the two are never spelled the same way.
  - Takes no terms. The question is about one file, and which file is
    the C(path) option.
options:
  path:
    description:
      - The file to read the answer from, as an absolute path.
      - Defaults to C(/etc/shells). Give the C(shells_path) the
        producer was pointed at where it was pointed somewhere else.
    type: str
    default: /etc/shells
  host:
    description:
      - Read C(o0_paths) from another host's variables rather than
        the current host's.
      - A host that has not gathered the fact answers B(unknown).
    type: str
notes:
  - This lookup reads the C(o0_paths) fact from the variable namespace
    and runs nothing on the host. Gather it first; a namespace holding
    no C(o0_paths) was never asked about anything, so the answer is
    B(unknown).
  - The lookup does fail when C(o0_paths) is present but is not a
    dictionary, when the entry at the path is neither null nor a
    mapping of observed facts, and when that entry carries a C(config)
    that is not a list.
  - An entry that exists but was never parsed - a path some other
    producer filed metadata for, with no C(config) on it - is
    B(unknown) rather than a host that names none. The file is there;
    nothing read it.
seealso:
  - module: o0_o.posix.facts
    description: Gather POSIX facts, C(o0_paths) among them
  - module: o0_o.posix.users
    description: Gather POSIX user and group information
  - plugin: o0_o.posix.commands
    plugin_type: lookup
    description: Resolve command names against a POSIX search path
"""

EXAMPLES = r"""
- name: Gather the facts the lookup reads
  o0_o.posix.facts:
    gather_subset: ['users']

- name: Show the login shells the host names
  ansible.builtin.debug:
    msg: "{{ lookup('o0_o.posix.shells').shells }}"

- name: Answer whether a user's shell is a login shell
  ansible.builtin.debug:
    msg: >-
      {{ lookup('o0_o.posix.user', 'o0-o')['shell'] in answer['shells'] }}
  vars:
    answer: "{{ lookup('o0_o.posix.shells') }}"
  when: answer['state'] == 'named'

- name: Tell a host that names none from one that was never asked
  ansible.builtin.assert:
    that:
      - answer['shells'] is defined
    fail_msg: >-
      Nothing gathered says what this host calls a login shell;
      gather the facts before asking.
  vars:
    answer: "{{ lookup('o0_o.posix.shells') }}"

- name: Warn where the host lists no login shells at all
  ansible.builtin.debug:
    msg: '{{ inventory_hostname }} has /etc/shells and names nothing'
  vars:
    answer: "{{ lookup('o0_o.posix.shells') }}"
  when:
    - answer['state'] == 'named'
    - answer['shells'] | length == 0

- name: Read a shells file the producer was pointed at
  ansible.builtin.debug:
    msg: >-
      {{ lookup('o0_o.posix.shells', path='/usr/local/etc/shells') }}

- name: Read the answer from another host's facts
  ansible.builtin.debug:
    msg: "{{ lookup('o0_o.posix.shells', host='webserver1') }}"
"""

RETURN = r"""
_raw:
  description:
    - One answer, about the one file that was asked about.
    - The tri-state reads off C(shells), following the collection's
      absence contract. A list is what the file names; C(null) is a
      file confirmed not to exist; and no C(shells) key at all is an
      unknown, nothing having parsed that path. C(state) names the
      same three answers in a word.
    - An unknown never carries a C(shells) key. A caller can therefore
      write C(answer.shells is defined) for "the store knows" and
      C(answer.shells == []) for "the host names none".
  type: dict
  contains:
    path:
      description: The file the answer is about.
      returned: always
      type: str
      sample: /etc/shells
    state:
      description:
        - C(named) where the store holds the parsed file, C(missing)
          where the store holds it as not existing, and C(unknown)
          where nothing parsed that path.
      returned: always
      type: str
      choices:
        - named
        - missing
        - unknown
      sample: named
    shells:
      description:
        - The login shells the file names, in the order it names
          them - an empty list where it names none - or C(null) where
          the file does not exist.
        - Absent from the answer where the state is C(unknown).
      returned: when the state is C(named) or C(missing)
      type: list
      elements: str
      sample:
        - /bin/sh
        - /bin/zsh
  sample:
    path: /etc/shells
    state: named
    shells:
      - /bin/sh
      - /bin/zsh
"""

from typing import Any, Optional

from ansible.errors import AnsibleLookupError
from ansible.plugins.lookup import LookupBase

from ansible_collections.o0_o.core.plugins.module_utils import (
    VarsLookupBase,
)
from ansible_collections.o0_o.posix.plugins.module_utils import canonicalize

# The three answers the file can get.  They are the absence contract
# in a word: a list parsed, a null gathered, or a path never parsed.
NAMED = "named"
MISSING = "missing"
UNKNOWN = "unknown"

# Where a host names its login shells, unless a producer was pointed
# somewhere else
DEFAULT_PATH = "/etc/shells"


class LookupModule(LookupBase, VarsLookupBase):
    """Answer with the login shells a host names."""

    def run(
        self,
        terms: list[Any],
        variables: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Perform the lookup.

        :param list terms: Nothing; the lookup takes no terms
        :param dict variables: Available Ansible variables
        :returns list: The one tri-state answer, in a list of one
        :raises AnsibleLookupError: If a term was given, if an
            argument cannot be made sense of, or if the store or the
            entry is not the shape it has to be
        """
        if terms:
            raise AnsibleLookupError(
                f"The shells lookup takes no terms, got {list(terms)!r}."
                f" It asks about one file, and which file is the 'path'"
                f" option"
            )

        path = self._validated_path(kwargs.pop("path", DEFAULT_PATH))

        # The store the answer is read from. The default makes an
        # absent fact a store that was never asked anything, so the
        # answer is unknown
        paths = self.lookup_var("o0_paths", default={}, **kwargs)

        if not isinstance(paths, dict):
            raise AnsibleLookupError(
                f"'o0_paths' fact is not a dictionary, got "
                f"{type(paths).__name__}"
            )

        return [self._answer(path, paths)]

    def _validated_path(self, path: Any) -> str:
        """Fail unless the file asked about is one the store can key.

        :param Any path: The path argument as it was given
        :returns str: The path in the form the store keys it by
        :raises AnsibleLookupError: If it is not an absolute path
        """
        if not isinstance(path, str) or not path.startswith("/"):
            raise AnsibleLookupError(
                f"'path' must be an absolute path, got {path!r}. The"
                f" store is keyed by whole paths, and a relative one"
                f" names nothing on its own"
            )

        return canonicalize(path)

    def _answer(self, path: str, paths: dict[str, Any]) -> dict[str, Any]:
        """Answer for one file from the store, in three states.

        A path the store never mentioned and a path it describes
        without ever parsing are the same answer: nothing read the
        file, so nothing here can say what it names.  A null is the
        other kind of certainty - the file is not there - and an
        empty list is the third, a file that is there and names none.

        :param str path: The file to answer about
        :param dict[str, Any] paths: The o0_paths store
        :returns dict[str, Any]: The answer, keyed path, state, shells
        :raises AnsibleLookupError: If the entry is neither null nor a
            mapping, or carries a config that is not a list
        """
        if path not in paths:
            return {"path": path, "state": UNKNOWN}

        entry = paths[path]

        if entry is None:
            return {"path": path, "state": MISSING, "shells": None}

        if not isinstance(entry, dict):
            raise AnsibleLookupError(
                f"The 'o0_paths' entry for {path!r} is neither null nor"
                f" a mapping of observed facts, got"
                f" {type(entry).__name__}: {entry!r}"
            )

        if "config" not in entry:
            return {"path": path, "state": UNKNOWN}

        shells = entry["config"]

        if not isinstance(shells, list):
            raise AnsibleLookupError(
                f"The 'o0_paths' entry for {path!r} carries a 'config'"
                f" that is not a list of login shells, got"
                f" {type(shells).__name__}: {shells!r}"
            )

        return {"path": path, "state": NAMED, "shells": list(shells)}
