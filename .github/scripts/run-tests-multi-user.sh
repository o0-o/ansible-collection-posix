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

# Source the venv
. .venv/bin/activate

echo "Running $test_type tests as root user..."
ansible-test "$test_type" --venv --python "$python_version"

# Create a test user if it doesn't exist
if ! id testuser >/dev/null 2>&1; then
	echo "Creating test user..."
	if [ -f /etc/alpine-release ]; then
		adduser -D -s /bin/sh testuser
	else
		useradd -m -s /bin/sh testuser
	fi
fi

# Create a test directory in the user's home directory
echo "Setting up test environment for non-root user..."
test_user_home=$(getent passwd testuser | cut -d: -f6)
test_dir="$test_user_home/ansible-test"
mkdir -p "$test_dir"
cp -a . "$test_dir/"
chown -R testuser:testuser "$test_dir"

# Run tests as non-root user
echo "Running $test_type tests as non-root user..."
echo "Debugging environment as testuser..."
su testuser -c "cd '$test_dir' && pwd && whoami && ls -la .venv" || echo "Basic commands failed"
echo "Debugging venv activation..."
su testuser -c "cd '$test_dir' && . .venv/bin/activate && echo 'venv activated' && which python" || echo "venv activation failed"
echo "Debugging ansible-test..."
su testuser -c "cd '$test_dir' && . .venv/bin/activate && which ansible-test" || echo "which ansible-test failed"
echo "Running actual tests..."
su testuser -c "cd '$test_dir' && . .venv/bin/activate && ansible-test $test_type --venv --python $python_version"

# Cleanup
cd /
rm -rf "$test_dir"