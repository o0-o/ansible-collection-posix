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


class ModuleDocFragment:
    # This fragment adds notes and no options. ansible-core requires
    # every documentation fragment to carry one key or the other, so
    # the empty mapping below is what lets a fragment that is entirely
    # prose load at all.
    DOCUMENTATION = """
    options: {}
    notes:
      - >-
        C(evidence) is the one vocabulary this collection names
        provenance in. Every fact it composes carries it, and wherever
        it appears it is a mapping keyed by kind of origin, with the
        same three kinds. A consumer reads the kind off the key it
        asked for, never off the shape of what it finds there.
      - >-
        C(files) names the paths that were read. Each is a key of
        C(o0_paths), so an entry joins against the file it came out of
        rather than being told that some file exists somewhere.
      - >-
        C(commands) names the commands that were consulted, by name
        and not by argv. Argv would say what was typed, and what was
        typed is a debugging concern rather than a fact - the
        configuration sweep is dozens of invocations of one command,
        and gathering a directory's metadata is one invocation per
        file, so either would bury the answer under its own
        repetitions. The name answers the question a consumer has,
        which is what was consulted; what it said is the fact itself.
        The name is argv's first word, reduced to its base name, so a
        command found at a path is filed under the command it is.
      - >-
        C(config) names the POSIX configuration variables that were
        read, mapped to the values they answered with at gather time.
        Each key is a key of C(o0_os.config) and each value is typed
        the way that fact types one, an integer where the host printed
        a number, so the two join by variable name and find one answer
        rather than two spellings of it. The value is in the evidence
        rather than pointed at, because a producer that names a
        variable may run without the configuration subset ever being
        gathered, and support that dangles is no support at all.
      - >-
        A value appears under C(config) only where it evidences
        something else. A compliance verdict is a claim about the host
        that a variable supports, so the verdict carries the variable;
        C(o0_os.config) publishes those same variables as the fact
        they are, and a fact is not evidence for itself. The same
        holds for every published answer - what C(sh_posix_compliant)
        says, what each filesystem answers about itself - which is why
        those name the command that asked and nothing more.
      - >-
        A producer carries the subkey of every kind it attempts. An
        empty list or mapping says the kind was attempted and
        contributed nothing, which is the discipline every other fact
        here holds to; a kind absent altogether says it is not one
        this producer has. C(o0_users) reads files and runs commands
        and is composed from no configuration variable, so its entries
        carry two kinds and not the third. Each list is sorted and
        holds one of each name.
      - >-
        Evidence attaches where provenance varies. A user or group
        entry carries its own, because one host may name a user in a
        file and another resolve it with a command; a compliance
        standard carries its own, because the standards are decided by
        different probes; an C(o0_shells) row carries its own, because
        a row is one shell observed out of one home. Where a single
        gather produced a whole section - C(o0_os), C(o0_network),
        C(o0_storage) - the section carries one record rather than
        every entry under it repeating the same answer. Several
        subsets may answer for one section, and the section's evidence
        is the union of what each of them consulted.
      - >-
        The three kinds are the whole vocabulary, and a collection
        gathering these same facts by other means names its origins in
        them rather than inventing a fourth. A datum that is not a
        path read, a command consulted, or a configuration variable
        answered is a finding rather than evidence, and belongs beside
        the verdict it is part of - the way a standard's C(missing)
        list sits beside its C(supported), evidenced by the lookups
        that missed rather than filed among them.
      - >-
        An evidence name derives from what was asked - argv's first
        word, reduced to its base name - and a request overrides that
        only where the derivation would answer the wrong question. A
        probe whose logic is a script would name the interpreter that
        read the script back, so such a probe names the commands it
        asks with instead: the permission probe names C(test), and
        C(su) where it drops identity; the resolution walk names
        C(cd), C(pwd) and C(ls). Where the shell is itself the
        subject, the interpreter is the answer and stays - the
        compliance sweep tests C(/bin/sh) and the C(o0_shells) probes
        ask a shell about itself, so both name the shell.
      - >-
        C(origins) travels with C(evidence) and answers the other half
        of the same question. Evidence says what was consulted;
        origins says who did the consulting, as a sorted list of the
        module FQCNs that composed the thing it sits on. A collection
        contributing to a fact this one publishes names itself there
        rather than inventing a field of its own.
      - >-
        The two attach at the same granularity, for the same reason
        and by the same rule: origins goes wherever a composition has
        already said what it consulted. So a user entry, a group
        entry, an C(o0_paths) entry, an C(o0_shells) row and a
        compliance standard each carry their own, because each has its
        own answer; and C(o0_os), C(o0_network), C(o0_hardware) and
        C(o0_storage) carry one for the section, because one gather
        produced it. A mapping that says nothing was consulted claims
        no producer.
      - >-
        Both accumulate where every other field is replaced. A section
        several subsets answer for was consulted several ways and
        composed by several producers - C(o0_os) names the C(uname)
        that answered for its kernel, the C(date) for its timezone and
        the C(getconf) for its configuration - and a record that let
        the last of them win would claim a fraction of what happened.
        The parser that composed a fact and the module that published
        it both belong in it, so a gather's section routinely names
        two or three modules and a standalone module's names one.
    """
