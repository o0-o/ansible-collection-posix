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
# Script to install collection dependencies with retry logic
#
# This script runs ansible-galaxy collection install to install
# dependencies from galaxy.yml. It retries up to 3 times with
# progressive delays in case of network issues.
#
# Usage: . .github/scripts/install-collection-deps.sh

# Install collection dependencies with retry
# (without --force to avoid overwriting)
echo "Installing collection dependencies..."
echo "Current directory: $(pwd)"
echo "Checking galaxy.yml exists:"
if [ -f galaxy.yml ]; then
	echo "  galaxy.yml found"
	echo "  Dependencies listed in galaxy.yml:"
	grep -A10 "^dependencies:" galaxy.yml || echo "  No dependencies section found"
else
	echo "  WARNING: galaxy.yml not found!"
fi

echo "Current Ansible collections path:"
ansible-galaxy collection list --format yaml | head -n 5

n=0
deps_installed=0
while [ $n -lt 3 ] && [ $deps_installed -eq 0 ]; do
	if [ $n -gt 0 ]; then
		sleep_time=$((n * 15))
		echo "Retrying dependency installation (attempt $((n+1))/3)" \
			"in ${sleep_time} seconds..."
		sleep "$sleep_time"
	fi
	echo "Running: ansible-galaxy collection install . -vvv"
	if ansible-galaxy collection install . -vvv; then
		deps_installed=1
		echo "Collection dependencies installed successfully"
		echo "Verifying o0_o.utils installation:"
		ansible-galaxy collection list o0_o.utils || echo "  o0_o.utils not found"
	else
		echo "  ansible-galaxy collection install failed with exit code $?"
	fi
	n=$((n+1))
done
if [ $deps_installed -eq 0 ]; then
	echo "ERROR: Failed to install collection dependencies after 3 attempts"
	exit 1
fi