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
    returned by the C(o0_o.posix.which), C(o0_o.posix.shells) and
    C(o0_o.posix.users) modules. The search path to follow is read
    from C(o0_shells), which C(o0_o.posix.facts) and
    C(o0_o.posix.shells) publish.
  - This is a simulation, and a search path is session-scoped, so the
    lookup says which session it simulates rather than leaving it to
    be inferred. Every gathered answer here is a B(login) search path
    - what a login shell built out of the files it read. It is not
    what a C(become) session would search - C(sudo) replaces C(PATH)
    with C(secure_path) where the sudoers file sets one and C(doas)
    has its own rules, and neither file is gathered by anything here.
    For the search a privileged session would really do, run
    M(o0_o.posix.which) on the host, or read the resolutions
    C(o0_paths) already holds from the gather that made them.
  - The answer is tri-state. A name is B(resolved) when the fact says
    the first candidate reached is executable; it is B(missing) when
    the fact answers null - asked about, does not exist - at every
    candidate; and it is B(unknown) when a candidate that could have
    answered first was never gathered, because a store cannot report
    what it was never asked.
  - C(executable) in the store is a mapping of uid to what that uid
    was told, because whether a file will run is a question the kernel
    answers per asker. A candidate any uid could run is a resolution,
    since the search is looking for a file that runs; a candidate
    every uid that asked was refused is passed over; and a candidate
    nobody asked about is what leaves the answer unknown.
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
      - Defaults to the host's own login default - the C(PATH) the
        shell probed out of C(/dev/null) reported, read from
        C(o0_shells). Every POSIX host has C(/dev/null) and none of
        them has it as a directory, so that row is what a login gets
        before any user's dot files enter into it, which makes it a
        fact about the host rather than a guess about a session.
      - Two shells probed out of C(/dev/null) that report different
        search paths are ambiguous and fail, naming them.
      - An empty string is one empty entry, not an empty path, and a
        list with no elements is a search path nothing can resolve
        in, so every name is a confirmed absence.
      - Mutually exclusive with C(user).
    type: raw
  user:
    description:
      - Whose login C(PATH) to follow, by UID (int) or username
        (str).
      - The user's C(o0_users) entry names the pair - the C(shell)
        they log in with and the C(home) it starts from - and the
        C(o0_shells) row that pair was probed at is what says what
        their login built. A user whose pair was never probed answers
        unknown for every name, which is how a user with no gathered
        environment answered before.
      - A gather probes the login of root and of the user it connected
        as. To have another user's, gather as them - a task with
        C(become) and C(become_user) set to them - and their row is
        there to join against, the same delegation any user-scoped
        fact takes.
      - This is that user's login path and not what they would search
        under C(sudo). See the description.
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
      - Read C(o0_paths), C(o0_shells) and C(o0_users) from another
        host's variables rather than the current host's.
      - A host that has not gathered the facts answers unknown for
        every name.
    type: str
notes:
  - This lookup reads the C(o0_paths), C(o0_shells) and C(o0_users)
    facts from the variable namespace and runs nothing on the host.
    Gather them first; a namespace holding no C(o0_paths) was never
    asked about anything, so every name answers unknown.
  - The lookup does fail when C(o0_paths), C(o0_shells) or
    C(o0_users) is present but is not a dictionary, and when an
    C(o0_paths) entry is neither null nor a mapping.
  - Producers validate the search path they gather and refuse to
    record an entry they cannot key; this lookup validates the search
    path it is asked to follow. A literal C(~) is inert as a fact and
    an error as a search path.
  - One caveat can mislead the answer, and only one. Reaching a file
    is a property of the user reaching it, so a name the store
    resolves may not resolve for a user who cannot search one of the
    directories along the way. The store records which uids were told
    the file itself will run; it records nothing about who can walk
    the directories to get to it, and that is the whole of the
    caveat.
seealso:
  - module: o0_o.posix.facts
    description: Gather POSIX facts, C(o0_paths) among them
  - module: o0_o.posix.shells
    description: >-
      Run the host's login shells, which is what reports the search
      paths this lookup follows
  - module: o0_o.posix.which
    description: >-
      Resolve one command on the host, in the session the task really
      runs in
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

- name: Follow another user's login PATH
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
    SHELL_SYSTEM_HOME,
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


def _runs(executable: Any) -> Optional[bool]:
    """Whether the store says a candidate will run, or will not say.

    ``executable`` is a mapping of uid to the answer that uid was
    given, because whether a file runs is the kernel's answer to
    whoever asked rather than a property of the file alone.  The
    search is looking for a file that runs, so one uid told yes is
    enough to stop at; every uid that asked told no is a file to walk
    past; and a mapping with nobody in it, or none at all, is nobody
    having asked.

    :param Any executable: The entry's executable field, whatever it
        holds
    :returns Optional[bool]: True where some uid was told the file
        runs, False where every uid that asked was refused, and None
        where nothing was asked
    """
    if not isinstance(executable, dict) or not executable:
        return None

    answers = [answer for answer in executable.values() if answer is not None]

    if not answers:
        return None

    return any(answer is True for answer in answers)


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
                " path given outright is nobody's login"
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
        """Read the login search path the shell probes reported.

        A PATH is what a login shell built, out of the files it read
        in the home it was started from, so the answer lives on the
        ``o0_shells`` row for that pair and not on the user.  Naming a
        user joins their passwd entry to their own row - their shell
        and their home - and naming none reads the system row, the
        shell the probe ran out of ``/dev/null``, which is the host's
        own login default before anybody's dot files enter into it.

        :param Any user: UID (int) or username (str), or None
        :returns Optional[list[Any]]: The entries in search order, or
            None where no probed row answers
        :raises AnsibleLookupError: If a fact is not a dictionary, or
            if no user was named and the system rows disagree
        """
        shells = self.lookup_var("o0_shells", default={}, **kwargs)

        if not isinstance(shells, dict):
            raise AnsibleLookupError(
                f"'o0_shells' fact is not a dictionary, got "
                f"{type(shells).__name__}"
            )

        if user is None:
            return self._system_path(shells)

        users = self.lookup_var("o0_users", default={}, **kwargs)

        if not isinstance(users, dict):
            raise AnsibleLookupError(
                f"'o0_users' fact is not a dictionary, got "
                f"{type(users).__name__}"
            )

        return self._login_path(shells, lookup_user(user, users))

    def _system_path(
        self, shells: dict[str, Any]
    ) -> Optional[list[Any]]:
        """Read the host's own login default out of the system rows.

        Every POSIX host has ``/dev/null`` and none of them has it as
        a directory, so a shell run out of it reports what a login
        gets before any user's dot files are read.  That is a fact
        about the host rather than a guess about a session, which is
        what makes it the default here.

        Two shells probed out of it can disagree, a gather having
        named one shell and a later one another.  Which of them a
        command would be run under is not settled here, so the caller
        is asked to settle it.

        :param dict[str, Any] shells: The o0_shells fact
        :returns Optional[list[Any]]: The entries in search order, or
            None where no system row carries a PATH
        :raises AnsibleLookupError: If two system rows disagree
        """
        found = {
            shell: path
            for shell, entry in shells.items()
            for path in [self._row_path(entry, SHELL_SYSTEM_HOME)]
            if path is not None
        }

        if len(set(found.values())) > 1:
            named = ", ".join(sorted(repr(shell) for shell in found))
            raise AnsibleLookupError(
                f"The shells probed out of {SHELL_SYSTEM_HOME} report"
                f" different search paths ({named}), so which one a"
                f" command would be run under is not settled here."
                f" Name a user with 'user', or give a search path with"
                f" 'path'"
            )

        for path in found.values():
            return path.split(":")

        return None

    def _login_path(
        self, shells: dict[str, Any], entry: Any
    ) -> Optional[list[Any]]:
        """Read one user's login search path off their own row.

        The passwd entry names the pair - the shell the user logs in
        with and the home it starts from - and the row that pair was
        probed at is the only place that says what the login built.  A
        user whose pair was never probed answers nothing, the way a
        user with no gathered environment used to.

        :param dict[str, Any] shells: The o0_shells fact
        :param Any entry: The user's o0_users entry, or None
        :returns Optional[list[Any]]: The entries in search order, or
            None where the pair names no probed row
        """
        if not isinstance(entry, dict):
            return None

        shell = entry.get("shell")
        home = entry.get("home")

        if not isinstance(shell, str) or not isinstance(home, str):
            return None

        path = self._row_path(shells.get(shell), home)

        return None if path is None else path.split(":")

    @staticmethod
    def _row_path(entry: Any, home: Any) -> Optional[str]:
        """Read the PATH one probed row reported, if it has one.

        :param Any entry: One o0_shells entry, whatever it holds
        :param Any home: The home whose row to read
        :returns Optional[str]: The PATH the row reported, or None
            where the entry, the row, or the variable is not there
        """
        if not isinstance(entry, dict):
            return None

        homes = entry.get("homes")

        if not isinstance(homes, dict):
            return None

        row = homes.get(home)

        if not isinstance(row, dict):
            return None

        environment = row.get("env")

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
        every uid that asked was refused is passed over the same way,
        because a file that will not run is not what the search is
        looking for.

        A candidate the store has nothing to say about - never
        gathered, or gathered without anybody having asked whether it
        runs - is why the third state exists.  Something may or may
        not be there, ahead of whatever the walk finds later, so the
        answer is unknown rather than a path the host might not agree
        with.

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

            executable = _runs(entry.get("executable"))

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
