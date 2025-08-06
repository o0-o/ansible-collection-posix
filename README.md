# o0_o.posix

[![CI](https://github.com/o0-o/ansible-collection-posix/actions/workflows/ci.yml/badge.svg)](https://github.com/o0-o/ansible-collection-posix/actions/workflows/ci.yml)
[![Ansible Galaxy](https://img.shields.io/ansible/collection/v/o0_o/posix.svg?color=brightgreen&label=ansible%20galaxy)](https://galaxy.ansible.com/o0_o/posix)

Ansible Collection for POSIX-compatible modules and action plugins with raw fallback support.

## Overview

The `o0_o.posix` collection provides enhanced versions of common Ansible modules with quality-of-life improvements and built-in fallback logic for environments that lack a Python interpreter. These tools are especially useful for bootstrapping hosts in mixed environments that include minimal or embedded systems.

### Key Features

- Fallback to raw POSIX tools (`sh`, `cat`, etc.) when Python is missing
- Check mode, async, and idempotence support where applicable
- Comprehensive unit and integration test coverage
- _Mostly_ drop-in replacements for `ansible.builtin.command`, `ansible.builtin.slurp` and `ansible.builtin.lineinfile` modules with some quality-of-life enhancements

## Plugins

### Action Plugins

| Name                | Description                                                                 |
|---------------------|-----------------------------------------------------------------------------|
| `command`           | Enhanced `command` module with raw execution fallback and _nearly_ full param parity |
| `slurp64`           | Read remote file contents with automatic base64 decoding, fallback to raw `cat`       |
| `lineinfile_dedupe` | Manage lines with deduplication, regex support, and enforced relative insertion; fallback included |
| `template`          | Drop-in replacement for `template` with raw fallback and enhanced check mode and force logic |

### Module Stubs

These exist to support `ansible-doc` and collection metadata. Do not use directly.

- `command`: see [`plugins/action/command.py`](plugins/action/command.py)
- `slurp64`: see [`plugins/action/slurp64.py`](plugins/action/slurp64.py)
- `lineinfile_dedupe`: see [`plugins/action/lineinfile_dedupe.py`](plugins/action/lineinfile_dedupe.py)
- `template`: see [`plugins/action/template.py`](plugins/action/template.py)

## Usage

### `command`

```yaml
- name: Run a command with fallback support
  o0_o.posix.command:
    argv: ["uptime"]

- name: Run a shell command with variable expansion
  o0_o.posix.command:
    cmd: "echo $HOME"
    _uses_shell: true
    expand_argument_vars: true
```

### `slurp64`

```yaml
- name: Read file content with slurp64
  o0_o.posix.slurp64:
    src: "/etc/hosts"
```

### `lineinfile_dedupe`

```yaml
- name: Insert a line if not already present and deduplicate
  o0_o.posix.lineinfile_dedupe:
    path: /etc/myapp.conf
    line: "enabled=true"
    regexp: '^enabled='
    create: true
    dedupe: true

- name: Remove all matching lines
  o0_o.posix.lineinfile_dedupe:
    path: /etc/myapp.conf
    regexp: '^debug='
    state: absent

- name: Insert a line after a comment section
  o0_o.posix.lineinfile_dedupe:
    path: /etc/myapp.conf
    line: "enabled=true"
    insertafter: '^# Feature toggles'
    create: true
```

### `template`

```yaml
- name: Render a template with fallback if Python is missing
  o0_o.posix.template:
    src: hello.j2
    dest: /tmp/hello.txt
    mode: '0644'
  vars:
    greeting: Hello world
```

## Installation

Install from Ansible Galaxy:

```sh
ansible-galaxy collection install o0_o.posix
```

## Development & Testing

The `o0_o.posix` collection is tested on Python versions 3.9–3.13.

To run sanity tests:

```sh
ansible-test sanity --venv  # or --docker if you prefer
```

To run unit tests:

```sh
ansible-test units --venv  # or --docker if you prefer
```

To run integration tests:

```sh
ansible-test integration --venv  # or --docker if you prefer
```

# License

Licensed under the [GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.txt) or later (GPLv3+)
