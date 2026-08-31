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
        provenance in. Wherever a fact carries it - an C(o0_users) or
        C(o0_groups) entry, a standard of C(o0_os.compliance) - it is
        a mapping keyed by kind of origin, and the kinds are the same
        three everywhere. A consumer reads the kind off the key it
        asked for, never off the shape of what it finds there.
      - >-
        C(files) names the paths that were read. Each is a key of
        C(o0_paths), so an entry joins against the file it came out of
        rather than being told that some file exists somewhere.
      - >-
        C(commands) names the commands that were run, each as the argv
        it was executed with rather than as a string. Argv is the form
        a command was executed in, a string would imply a shell
        reading it back, and Jinja membership answers on list elements
        - so a play asks what ran without parsing anything to find
        out.
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
        A producer carries the subkey of every kind it attempts. An
        empty list or mapping says the kind was attempted and
        contributed nothing, which is the discipline every other fact
        here holds to; a kind absent altogether says it is not one
        this producer has. C(o0_users) reads files and runs commands
        and is composed from no configuration variable, so its
        entries carry two kinds and not the third.
      - >-
        The three kinds are the whole vocabulary, and a collection
        gathering these same facts by other means names its origins in
        them rather than inventing a fourth. A datum that is not a
        path read, a command run, or a configuration variable answered
        is a finding rather than evidence, and belongs beside the
        verdict it is part of - the way a standard's C(missing) list
        sits beside its C(supported), evidenced by the lookups that
        missed rather than filed among them.
    """
