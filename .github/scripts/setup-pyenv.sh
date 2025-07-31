#!/bin/bash
# vim: ts=2:sw=2:sts=2:et:ft=sh
# -*- mode: sh; tab-width: 2; indent-tabs-mode: nil; -*-
#
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later
# (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
#
# Copyright (c) 2025 oØ.o (@o0-o)
#
# This file is part of the o0_o.posix Ansible Collection.

set -e

# Install build dependencies for pyenv based on OS
case "$1" in
  debian:*|ubuntu:*)
    export DEBIAN_FRONTEND=noninteractive
    export TZ=UTC
    apt-get update &&
    apt-get install -y \
      -o Dpkg::Options::="--force-confdef" \
      -o Dpkg::Options::="--force-confold" \
      bash git curl tar findutils build-essential libssl-dev \
      zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev \
      libncursesw5-dev xz-utils tk-dev libxml2-dev \
      libxmlsec1-dev libffi-dev liblzma-dev
    ;;
  fedora:*|*rockylinux:*|almalinux:*|*centos*)
    dnf install -y --allowerasing \
      bash git curl tar findutils gcc make openssl-devel \
      bzip2-devel libffi-devel zlib-devel readline-devel \
      sqlite-devel xz-devel
    ;;
  opensuse/*)
    zypper install -y \
      bash git curl tar gzip findutils gcc make openssl-devel \
      libbz2-devel libffi-devel zlib-devel readline-devel \
      sqlite3-devel xz-devel gawk coreutils
    ;;
  archlinux)
    pacman -Sy --noconfirm \
      bash git curl tar findutils base-devel openssl zlib bzip2 \
      libffi readline sqlite xz
    ;;
  alpine:*)
    apk add --no-cache \
      bash git curl tar findutils build-base openssl-dev \
      zlib-dev bzip2-dev libffi-dev readline-dev sqlite-dev \
      xz-dev coreutils
    ;;
esac

# Install pyenv
export PYENV_ROOT="/root/.pyenv"
curl -s https://pyenv.run | bash
export PATH="/root/.pyenv/bin:$PATH"
eval "$(pyenv init - sh)"

# Install latest patch versions for each major.minor
py_vers=""
for py in 3.13 3.12 3.11 3.10 3.9; do
  pyenv install $py
  py_vers="$py_vers $py"
done

pyenv global $py_vers

# Refresh pyenv shims
mkdir -p "$(pyenv root)/plugins"
git clone https://github.com/pyenv/pyenv-which-ext.git \
  "$(pyenv root)/plugins/pyenv-which-ext"
pyenv rehash

# Create venv with latest Python and install ansible-core
git config --global --add safe.directory \
  /root/ansible_collections/o0_o/posix
python -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install ansible-core