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
name: commands
short_description: Resolve command names against a POSIX search path
version_added: "2.0.0"
description:
  - Resolve command names against the C(o0_paths) fact, walking a
    search path in order the way the host's own command search walks
    it, without running anything on the host.
  - The C(o0_paths) fact is set by the C(o0_o.posix.facts) module and
    returned by the C(o0_o.posix.which) and C(o0_o.posix.users)
    modules.
  - The answer is tri-state. A name is B(resolved) when the fact says
    the first candidate reached is executable; it is B(missing) when
    the fact answers null - asked about, does not exist - at every
    candidate; and it is B(unknown) when a candidate that could have
    answered first was never gathered, because a store cannot report
    what it was never asked.
  - Those three are the collection's absence contract applied to an
    answer rather than to a store, and the C(path) key of each answer
    carries them the same way - absent, null, or a value. See the
    RETURN block.
  - Nothing here expands C(~). An entry beginning with C(~) is a
    relative entry naming a directory literally called C(~), which is
    all the host's own search makes of it too.
options:
  _terms:
    description:
      - Command names to resolve, written as they would be typed.
      - A name carrying a C(/) is a path rather than a name, and the
        search path does not apply to it, so it is refused rather
        than answered. The same goes for C(.) and C(..), which name
        no file of their own.
    required: true
    type: list
    elements: str
  path:
    description:
      - The search path to follow, either as a C(:)-separated string
        in the manner of C(PATH) or as a list of directories.
      - Defaults to the C(PATH) the C(environment) subset gathered
        for the user, read from C(o0_users).
      - An empty string is one empty entry, not an empty path, and a
        list with no elements is a search path nothing can resolve
        in, so every name is a confirmed absence.
      - Mutually exclusive with C(user).
    type: raw
  user:
    description:
      - Whose gathered C(PATH) to follow, by UID (int) or username
        (str).
      - Defaults to the one user whose facts carry an C(environment)
        holding a C(PATH). A namespace where several users do is
        ambiguous and fails, naming them; a namespace where none do
        answers unknown for every name.
      - Mutually exclusive with C(path).
    type: raw
  cwd:
    description:
      - The absolute directory that relative and empty search path
        entries resolve against, exactly as the working directory of
        the process running the command resolves them.
      - Supply it only for compatibility with a host whose C(PATH)
        really does carry such an entry. A relative entry makes the
        binary a play runs a function of the directory it runs from,
        so whoever can write into that directory picks the binary,
        and the empty entry - what a leading, a trailing, or a
        doubled C(:) writes - is the same hazard spelled invisibly.
        Both have been ill-advised for as long as they have existed.
        This option reproduces the semantics; it does not endorse
        them.
      - C(~) is not expanded here either, so an entry of C(~/bin)
        with C(cwd) set to C(/srv) searches C(/srv/~/bin) - a
        directory literally named C(~) - because that is what the
        host would search.
      - Without it, a relative or empty entry names nothing a fact
        store can key, and is handled per C(path_errors).
    type: str
  path_errors:
    description:
      - What to do with a search path entry that is not an absolute
        path, whether it was supplied or gathered.
      - C(strict) fails the lookup, C(warn) warns and drops the
        entry, and C(ignore) drops it silently, in the manner of the
        C(errors) keyword every lookup call takes.
      - It is not named C(errors) because Ansible reserves that
        keyword for the error handling of a lookup call as a whole
        and consumes it before any plugin sees it.
    type: str
    default: strict
    choices:
      - strict
      - warn
      - ignore
  host:
    description:
      - Read C(o0_paths) and C(o0_users) from another host's
        variables rather than the current host's.
      - A host that has not gathered the facts answers unknown for
        every name.
    type: str
notes:
  - This lookup reads the C(o0_paths) and C(o0_users) facts from the
    variable namespace and runs nothing on the host. Gather them
    first; a namespace holding no C(o0_paths) was never asked about
    anything, so every name answers unknown.
  - The lookup does fail when C(o0_paths) or C(o0_users) is present
    but is not a dictionary, and when an C(o0_paths) entry is neither
    null nor a mapping.
  - Producers validate the search path they gather and refuse to
    record an entry they cannot key; this lookup validates the search
    path it is asked to follow. A literal C(~) is inert as a fact and
    an error as a search path.
  - One caveat can mislead the answer, and only one. Execute
    permission is a property of a file, but reaching that file is a
    property of the user reaching it, so a name the store resolves
    for the user who gathered it may not resolve for another user who
    cannot search one of the directories along the way, or whom an
    ACL refuses where the mode does not. Per-user execute-bit
    variance inside a search path directory is the whole of it;
    everything else the search depends on is recorded.
seealso:
  - module: o0_o.posix.facts
    description: Gather POSIX facts, C(o0_paths) among them
  - module: o0_o.posix.which
    description: Resolve one command on the host and record the path
  - plugin: o0_o.posix.user
    plugin_type: lookup
    description: Look up user information by UID or username
"""

EXAMPLES = r"""
- name: Gather the facts the lookup reads
  o0_o.posix.facts:
    gather_subset: ['all']

- name: Resolve a command against the gathered PATH
  ansible.builtin.debug:
    msg: "{{ lookup('o0_o.posix.commands', 'ls') }}"

- name: Resolve several commands at once
  ansible.builtin.debug:
    msg: "{{ lookup('o0_o.posix.commands', 'ls', 'awk', wantlist=True) }}"

- name: Use a command only where it is known to be there
  ansible.builtin.command: rsync --version
  changed_when: false
  when: lookup('o0_o.posix.commands', 'rsync').state == 'resolved'

- name: Tell a confirmed absence from an ungathered store
  ansible.builtin.assert:
    that:
      - answer.state != 'unknown'
    fail_msg: >-
      Nothing gathered says where doas would be; gather the facts
      before asking.
  vars:
    answer: "{{ lookup('o0_o.posix.commands', 'doas') }}"

- name: Run the path a name resolved to rather than the name
  ansible.builtin.command: "{{ answer.path }} -u"
  changed_when: false
  vars:
    answer: "{{ lookup('o0_o.posix.commands', 'id') }}"
  when: answer.path is defined and answer.path is not none

- name: Resolve against a search path of the play's own choosing
  ansible.builtin.debug:
    msg: >-
      {{ lookup('o0_o.posix.commands', 'sendmail',
                path='/usr/sbin:/usr/libexec') }}

- name: Resolve against a search path given as a list
  ansible.builtin.debug:
    msg: >-
      {{ lookup('o0_o.posix.commands', 'zfs',
                path=['/sbin', '/usr/sbin']) }}

- name: Follow another user's gathered PATH
  ansible.builtin.debug:
    msg: "{{ lookup('o0_o.posix.commands', 'psql', user='postgres') }}"

- name: Read the answer from another host's facts
  ansible.builtin.debug:
    msg: "{{ lookup('o0_o.posix.commands', 'nft', host='firewall1') }}"

- name: Carry on past a PATH entry no store can key
  ansible.builtin.debug:
    msg: >-
      {{ lookup('o0_o.posix.commands', 'make', path_errors='warn') }}

- name: Reproduce the working directory a legacy PATH entry meant
  ansible.builtin.debug:
    msg: >-
      {{ lookup('o0_o.posix.commands', 'build',
                path='/usr/bin:.', cwd='/srv/project') }}
"""

RETURN = r"""
_raw:
  description:
    - One answer per command name asked for, in the order asked.
    - The tri-state reads off C(path), following the collection's
      absence contract. An absolute path is a resolution; C(null) is
      a confirmed absence, every candidate having been gathered as
      not existing; and no C(path) key at all is an unknown, some
      candidate never having been gathered. C(state) names the same
      three answers in a word.
    - An unknown never carries a C(path). A caller can therefore
      write C(answer.path is defined) for "the store knows" and
      C(answer.path is none) for "it is not there".
  type: list
  elements: dict
  contains:
    command:
      description: The command name that was asked about.
      returned: always
      type: str
      sample: ls
    state:
      description:
        - C(resolved) where the search path holds the command,
          C(missing) where every candidate is gathered as absent, and
          C(unknown) where the store cannot say.
      returned: always
      type: str
      choices:
        - resolved
        - missing
        - unknown
      sample: resolved
    path:
      description:
        - The absolute path the name resolves to, or C(null) where
          every candidate was gathered as absent.
        - Absent from the answer where the state is C(unknown).
      returned: when the state is C(resolved) or C(missing)
      type: str
      sample: /bin/ls
  sample:
    - command: ls
      state: resolved
      path: /bin/ls
    - command: doas
      state: missing
      path: null
    - command: rsync
      state: unknown
"""

import posixpath

from typing import Any, Optional, Union

from ansible.errors import AnsibleLookupError
from ansible.plugins.lookup import LookupBase

from ansible_collections.o0_o.utils.plugins.module_utils import (
    VarsLookupBase,
)
from ansible_collections.o0_o.posix.plugins.module_utils import (
    canonicalize,
    lookup_user,
)

# The three answers a name can get.  They are the absence contract in
# a word: a value found, a null gathered, or a store never asked.
RESOLVED = "resolved"
MISSING = "missing"
UNKNOWN = "unknown"

# What a search path entry that keys nothing costs, in the manner of
# the errors keyword a lookup call takes
PATH_ERRORS = ("strict", "warn", "ignore")

__all__ = ["LookupModule", "canonicalize"]


class LookupModule(LookupBase, VarsLookupBase):
    """Resolve command names against a POSIX search path."""

    def run(
        self,
        terms: list[Any],
        variables: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Perform the lookup.

        :param list terms: Command names to resolve
        :param dict variables: Available Ansible variables
        :returns list: One tri-state answer per name, in order
        :raises AnsibleLookupError: If an argument, a fact, or a
            search path entry cannot be made sense of
        """
        path = kwargs.pop("path", None)
        user = kwargs.pop("user", None)
        cwd = self._validated_cwd(kwargs.pop("cwd", None))
        path_errors = kwargs.pop("path_errors", "strict")

        if path_errors not in PATH_ERRORS:
            raise AnsibleLookupError(
                f"'path_errors' must be one of {', '.join(PATH_ERRORS)},"
                f" got {path_errors!r}"
            )

        if path is not None and user is not None:
            raise AnsibleLookupError(
                "'path' and 'user' are mutually exclusive: a search"
                " path given outright is nobody's environment"
            )

        # The store the answers are read from. The default makes an
        # absent fact a store that was never asked anything, so every
        # name answers unknown
        paths = self.lookup_var("o0_paths", default={}, **kwargs)

        if not isinstance(paths, dict):
            raise AnsibleLookupError(
                f"'o0_paths' fact is not a dictionary, got "
                f"{type(paths).__name__}"
            )

        if path is None:
            entries = self._gathered_path(user, **kwargs)
        else:
            entries = self._given_path(path)

        # A search path nobody gathered is not an empty search path:
        # it is an order this lookup does not know, so every name
        # stays unknown rather than being called absent
        dirs = (
            None
            if entries is None
            else self._search_dirs(entries, cwd, path_errors)
        )

        ret = []
        for term in terms:
            # Template the term to resolve any Jinja2 expressions
            term = self._templar.template(term)

            ret.append(self._answer(self._validated_name(term), dirs, paths))

        return ret

    def _validated_cwd(self, cwd: Any) -> Optional[str]:
        """Fail unless a supplied working directory is absolute.

        The working directory is the caller's own argument rather
        than something a host reported, so it is held to the store's
        keys strictly, whatever ``path_errors`` says about the
        entries it resolves.

        :param Any cwd: The cwd argument, or None where none was given
        :returns Optional[str]: The canonical cwd, or None
        :raises AnsibleLookupError: If cwd is not an absolute path
        """
        if cwd is None:
            return None

        if not isinstance(cwd, str) or not cwd.startswith("/"):
            raise AnsibleLookupError(
                f"'cwd' must be an absolute path, got {cwd!r}. It stands"
                f" in for the directory a command would run from, and a"
                f" relative one names nothing on its own"
            )

        return canonicalize(cwd)

    def _validated_name(self, term: Any) -> str:
        """Fail unless a term is a command name a search path applies to.

        A name carrying a ``/`` is a path, which the host would run
        without consulting any search path, and ``.`` and ``..`` name
        no file of their own.  The producers record nothing for
        either, so neither is answerable here.

        :param Any term: One term as it was asked for
        :returns str: The command name
        :raises AnsibleLookupError: If the term is not a name
        """
        if not isinstance(term, str) or not term:
            raise AnsibleLookupError(
                f"A term must be a command name, got"
                f" {type(term).__name__}: {term!r}"
            )

        if "/" in term:
            raise AnsibleLookupError(
                f"A term must be a command name, got the path {term!r}."
                f" A name carrying a '/' is resolved without a search"
                f" path, so read the path itself instead"
            )

        if term in (".", ".."):
            raise AnsibleLookupError(
                f"A term must be a command name, got {term!r}, which"
                f" names no file of its own"
            )

        return term

    def _given_path(self, path: Any) -> list[Any]:
        """Split a supplied search path into its entries.

        A string splits on ``:`` the way the host reads ``PATH``, so
        a leading, trailing, or doubled separator yields the empty
        entry rather than being tidied away.  A list is already its
        entries.

        :param Any path: The path argument as it was given
        :returns list[Any]: The entries, in search order
        :raises AnsibleLookupError: If the argument is neither form
        """
        if isinstance(path, str):
            return path.split(":")

        if isinstance(path, (list, tuple)):
            return list(path)

        raise AnsibleLookupError(
            f"'path' must be a ':'-separated search path or a list of"
            f" directories, got {type(path).__name__}: {path!r}"
        )

    def _gathered_path(self, user: Any, **kwargs: Any) -> Optional[list[Any]]:
        """Read the search path the environment subset gathered.

        The environment is gathered for one user, the one the play
        connects as, and it nests under that user's entry.  Naming a
        user reads that user's; naming none reads the only one there
        is, because a namespace where two users carry a PATH does not
        say which of them a command would be run as.

        :param Any user: UID (int) or username (str), or None
        :returns Optional[list[Any]]: The entries in search order, or
            None where no gathered PATH answers
        :raises AnsibleLookupError: If o0_users is not a dictionary,
            or if no user was named and several carry a PATH
        """
        users = self.lookup_var("o0_users", default={}, **kwargs)

        if not isinstance(users, dict):
            raise AnsibleLookupError(
                f"'o0_users' fact is not a dictionary, got "
                f"{type(users).__name__}"
            )

        if user is None:
            candidates = [
                entry
                for entry in users.values()
                if self._gathered_var(entry) is not None
            ]
            if len(candidates) > 1:
                named = ", ".join(
                    sorted(
                        repr(entry.get("name") or entry.get("uid"))
                        for entry in candidates
                    )
                )
                raise AnsibleLookupError(
                    f"Several users have a gathered PATH ({named}), so"
                    f" which one a command would be run as is not"
                    f" settled here. Name one with 'user', or give a"
                    f" search path with 'path'"
                )
            entry = candidates[0] if candidates else None
        else:
            entry = lookup_user(user, users)

        gathered = self._gathered_var(entry)

        return None if gathered is None else gathered.split(":")

    @staticmethod
    def _gathered_var(entry: Any) -> Optional[str]:
        """Read a user entry's gathered PATH, if it has one.

        :param Any entry: One o0_users entry, or None
        :returns Optional[str]: The PATH as gathered, or None where
            the entry carries no environment or no PATH in it
        """
        if not isinstance(entry, dict):
            return None

        environment = entry.get("environment")

        if not isinstance(environment, dict):
            return None

        path = environment.get("PATH")

        return path if isinstance(path, str) else None

    def _search_dirs(
        self,
        entries: list[Any],
        cwd: Optional[str],
        path_errors: str,
    ) -> list[str]:
        """Reduce search path entries to the directories they name.

        An absolute entry names a directory however it was written.
        Everything else - a relative entry, an unexpanded ``~``, and
        the empty entry a stray ``:`` writes - names a directory only
        in relation to a working directory, which a fact store does
        not have.  A supplied ``cwd`` lends it one, resolving the
        entry the way the running process would; without one the
        entry is an error, softened by ``path_errors``.

        :param list[Any] entries: The search path, in order
        :param Optional[str] cwd: The working directory to resolve
            against, or None
        :param str path_errors: strict, warn, or ignore
        :returns list[str]: The directories to search, in order
        :raises AnsibleLookupError: If an entry names no directory
            and path_errors is strict
        """
        dirs = []

        for entry in entries:
            if not isinstance(entry, str):
                self._reject(
                    f"The search path entry {entry!r} is not a string,"
                    f" got {type(entry).__name__}",
                    path_errors,
                )
                continue

            if entry.startswith("/"):
                dirs.append(canonicalize(entry))
                continue

            if cwd is not None:
                dirs.append(canonicalize(posixpath.join(cwd, entry)))
                continue

            self._reject(
                f"The search path entry {entry!r} is not an absolute"
                f" path. A relative entry, an unexpanded '~', and the"
                f" empty entry a leading, trailing, or doubled ':'"
                f" writes all name a directory only in relation to a"
                f" working directory, which a fact store has none of."
                f" Give 'cwd' to resolve it the way the running"
                f" process would, or drop it from the search path",
                path_errors,
            )

        return dirs

    def _reject(self, message: str, path_errors: str) -> None:
        """Fail, warn, or say nothing about an unusable entry.

        :param str message: What is wrong with the entry
        :param str path_errors: strict, warn, or ignore
        :raises AnsibleLookupError: If path_errors is strict
        """
        if path_errors == "strict":
            raise AnsibleLookupError(message)

        if path_errors == "warn":
            self._display.warning(message)

    def _answer(
        self,
        name: str,
        dirs: Optional[list[str]],
        paths: dict[str, Any],
    ) -> dict[str, Union[str, None]]:
        """Answer one command name from the store, in three states.

        The search walks the directories in order and stops at the
        first candidate the store calls executable, which is where
        the host's own search would stop.  A candidate the store
        holds as null is not there and the walk goes on; a candidate
        the store holds as present but not executable is passed over
        the same way, because a file that will not run is not what
        the search is looking for.

        A candidate the store has nothing to say about - never
        gathered, or gathered without its executable bit being
        settled - is why the third state exists.  Something may or
        may not be there, ahead of whatever the walk finds later, so
        the answer is unknown rather than a path the host might not
        agree with.

        :param str name: The command name
        :param Optional[list[str]] dirs: The directories to search in
            order, or None where the search path itself is unknown
        :param dict[str, Any] paths: The o0_paths store
        :returns dict: The answer, keyed command, state, and path
        :raises AnsibleLookupError: If an entry in the store is
            neither null nor a mapping of observed facts
        """
        if dirs is None:
            return {"command": name, "state": UNKNOWN}

        unsettled = False

        for directory in dirs:
            candidate = posixpath.join(directory, name)

            if candidate not in paths:
                unsettled = True
                continue

            entry = paths[candidate]

            if entry is None:
                continue

            if not isinstance(entry, dict):
                raise AnsibleLookupError(
                    f"The 'o0_paths' entry for {candidate!r} is neither"
                    f" null nor a mapping of observed facts, got"
                    f" {type(entry).__name__}: {entry!r}"
                )

            executable = entry.get("executable")

            if executable is True:
                # An earlier candidate nobody settled could have
                # answered first, so a resolution behind one names a
                # path the host might not have picked
                if unsettled:
                    break
                return {
                    "command": name,
                    "state": RESOLVED,
                    "path": candidate,
                }

            if executable is False:
                continue

            unsettled = True

        if unsettled:
            return {"command": name, "state": UNKNOWN}

        return {"command": name, "state": MISSING, "path": None}
