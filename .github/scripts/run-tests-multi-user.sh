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
# Script to run tests as both root and non-root users

set -eu

test_type="$1"  # units or integration
python_version="$2"

# Validate test type
case "$test_type" in
	units|integration)
		;;
	*)
		echo "Error: Invalid test type '$test_type'. Must be 'units' or 'integration'."
		exit 1
		;;
esac

# Create a test user if it doesn't exist
if ! id testuser >/dev/null 2>&1; then
	echo "Creating test user..."
	if [ -f /etc/alpine-release ]; then
		adduser -D -s /bin/sh testuser
	else
		useradd -m -s /bin/sh testuser
	fi
fi

# Set up clean collection copy for testuser before running any tests
echo "Setting up clean collection copy for testuser..."
test_user_home=$(getent passwd testuser | cut -d: -f6)
test_dir="$test_user_home/.ansible/collections/ansible_collections/o0_o/posix"
mkdir -p "$test_dir"
cp -a . "$test_dir/"
chown -R testuser:testuser "$test_user_home/.ansible"

# Source the venv
. .venv/bin/activate

echo "Running $test_type tests as root user..."
ansible-test "$test_type" --venv --python "$python_version"

# Run tests as non-root user
echo "Running $test_type tests as non-root user..."
echo "Setting up pyenv and venv for testuser..."
su testuser -c "
	export PYENV_ROOT=/opt/pyenv && 
	export PATH=/opt/pyenv/bin:\$PATH && 
	eval \"\$(pyenv init - sh)\" && 
	cd '$test_dir' && 
	pyenv local '$python_version' &&
	python -m venv .venv &&
	. .venv/bin/activate &&
	pip install --quiet --upgrade pip &&
	pip install --quiet ansible-core
"
echo "Running actual tests..."
su testuser -c "
	export PYENV_ROOT=/opt/pyenv && 
	export PATH=/opt/pyenv/bin:\$PATH && 
	eval \"\$(pyenv init - sh)\" && 
	cd '$test_dir' && 
	. .venv/bin/activate && 
	ansible-test '$test_type' --venv --python '$python_version'
"

