# o0_o.posix

[![CI](https://github.com/o0-o/ansible-collection-posix/actions/workflows/ci.yml/badge.svg)](https://github.com/o0-o/ansible-collection-posix/actions/workflows/ci.yml)
[![Ansible Galaxy](https://img.shields.io/ansible/collection/v/o0_o/posix.svg?color=brightgreen&label=Ansible%20Galaxy)](https://galaxy.ansible.com/o0_o/posix)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue.svg)](https://o0-o.github.io/ansible-collection-posix/)

POSIX-focused Ansible plugins with raw fallback support for minimal systems.

## Design

Two pillars generalize file operations, both with raw fallback for hosts
without Python: `o0_o.posix.read` subsumes stat- and slurp-style
observation, and `o0_o.posix.write` (in progress) will subsume template
rendering, line editing, copy, and file state — the modules they
generalize retire into them. The distinguishing arguments present in a
task select which part of the spec it is held to, so playbooks read as
plain verbs. Facts take the opposite shape: a top-level
`o0_o.posix.facts` aggregates the shared POSIX facts, and each fact
group also ships its own module, with filters and lookups where they
make sense. Mutation funnels through one well-tested module; observation
stays granular and composable.

## Documentation

Full documentation (modules, filters, usage, and examples) is published via
GitHub Pages (not versioned):

- https://o0-o.github.io/ansible-collection-posix/

The docs are generated with antsibull-docs and published continuously by CI.
Refer there for the complete list of plugins and options.

## Installation

```bash
ansible-galaxy collection install o0_o.posix
```

## Contributing

- Keep code formatted with black and passing flake8/yamllint.
- Run `ansible-test sanity`, `units`, and `integration` before submitting PRs.
- See the central AGENTS guide for contributor standards and testing guidance:
  https://github.com/o0-o/ansible-collections/blob/main/AGENTS.md

## License

GPL-3.0-or-later. See LICENSE.md for details.
