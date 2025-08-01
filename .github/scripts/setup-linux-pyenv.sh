#!/bin/sh
# vim: ts=8:sw=8:sts=8:noet:ft=sh
# -*- mode: sh; tab-width: 2; indent-tabs-mode: nil; -*-
#
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later
# (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
#
# Copyright (c) 2025 oØ.o (@o0-o)
#
# This file is part of the o0_o.posix Ansible Collection.
#
# Setup script for Linux containers in CI to install pyenv and Python versions

set -eu

# Install build dependencies for pyenv based on Linux distribution
case "$1" in
	debian:*|ubuntu:*)
		export DEBIAN_FRONTEND=noninteractive
		export TZ=UTC
		apt-get update -qq &&
		apt-get dist-upgrade -y -qq &&
		apt-get install -y -qq \
			-o Dpkg::Options::="--force-confdef" \
			-o Dpkg::Options::="--force-confold" \
			bash git curl tar findutils build-essential \
			libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
			libsqlite3-dev libncursesw5-dev xz-utils tk-dev \
			libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev \
			libyaml-dev locales shellcheck openssh-client
		# Generate en_US.UTF-8 locale
		locale-gen en_US.UTF-8
		update-locale LANG=en_US.UTF-8
		;;
	fedora:*|*rockylinux:*|almalinux:*|*centos*)
		# Enable EPEL for RHEL-based distros (not needed for Fedora)
		case "$1" in
			fedora:*)
				# Fedora has ShellCheck in main repos
				;;
			*)
				# All other RPM distros need EPEL
				dnf install -y -q --allowerasing epel-release
				;;
		esac
		dnf update -y -q &&
		dnf install -y -q --allowerasing \
			bash git curl tar findutils gcc make openssl-devel \
			bzip2-devel libffi-devel zlib-devel readline-devel \
			sqlite-devel xz-devel libyaml-devel glibc-langpack-en openssh-clients
		# Try to install ShellCheck, ignore if not available
		dnf install -y -q ShellCheck || echo "ShellCheck not available, skipping"
		;;
	opensuse/*)
		zypper update -y --quiet &&
		zypper install -y --quiet \
			bash git curl tar gzip findutils gcc make \
			openssl-devel libbz2-devel libffi-devel zlib-devel \
			readline-devel sqlite3-devel xz-devel libyaml-devel gawk coreutils \
			glibc-locale ShellCheck openssh
		;;
	archlinux)
		pacman -Syu --noconfirm --quiet &&
		pacman -S --noconfirm --quiet \
			bash git curl tar findutils base-devel openssl zlib \
			bzip2 libffi readline sqlite xz libyaml shellcheck openssh
		;;
	alpine:*)
		apk update --quiet &&
		apk upgrade --quiet &&
		apk add --no-cache --quiet \
			bash git curl tar findutils build-base openssl-dev \
			zlib-dev bzip2-dev libffi-dev readline-dev sqlite-dev \
			xz-dev yaml-dev coreutils shellcheck openssh-client
		;;
esac

# Set locale to avoid ansible-test warnings (after locale packages are installed)
# Alpine uses musl and doesn't have traditional locale support
case "$1" in
	alpine:*)
		export LANG=C.UTF-8
		export LC_ALL=C.UTF-8
		;;
	*)
		export LANG=en_US.UTF-8
		export LC_ALL=en_US.UTF-8
		;;
esac

# Install pyenv system-wide
export PYENV_ROOT="/opt/pyenv"
curl -s https://pyenv.run | bash >/dev/null
export PATH="/opt/pyenv/bin:$PATH"
eval "$(pyenv init - sh)" >/dev/null

# Install the specific Python version passed as argument
python_version="$2"
pyenv install "$python_version" >/dev/null
pyenv global "$python_version"

# Refresh pyenv shims
mkdir -p "$(pyenv root)/plugins"
git clone https://github.com/pyenv/pyenv-which-ext.git \
	"$(pyenv root)/plugins/pyenv-which-ext" >/dev/null
pyenv rehash

# Create venv with latest Python and install ansible-core
git config --global --add safe.directory \
	/root/ansible_collections/o0_o/posix

# Persist locale settings for ansible-test
case "$1" in
	alpine:*)
		echo "export LANG=C.UTF-8" >> /root/.profile
		echo "export LC_ALL=C.UTF-8" >> /root/.profile
		;;
	*)
		echo "export LANG=en_US.UTF-8" >> /root/.profile
		echo "export LC_ALL=en_US.UTF-8" >> /root/.profile
		;;
esac

python -m venv .venv
. .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet ansible-core
