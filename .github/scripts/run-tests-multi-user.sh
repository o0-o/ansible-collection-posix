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

INTEGRATION_TARGET="${INTEGRATION_TARGET:-}"  # optional integration target

# Validate test type
case "$TEST_TYPE" in
	units|integration)
		;;
	*)
		echo "Error: Invalid test type '$TEST_TYPE'. " \
			"Must be 'units' or 'integration'."
		exit 1
		;;
esac

# Create pyenv group and test user
echo "Setting up pyenv group and test user for ${TEST_TYPE} tests..."
if [ -f /etc/alpine-release ]; then
	addgroup pyenv
	adduser root pyenv
	adduser -D -s /bin/sh testuser
	adduser testuser pyenv
else
	groupadd pyenv
	usermod -a -G pyenv root
	useradd -m -s /bin/sh testuser
	usermod -a -G pyenv testuser
fi

# Set group permissions on pyenv directory
chgrp -R pyenv /opt/pyenv
chmod -R g+w /opt/pyenv
find /opt/pyenv -type d -exec chmod g+s {} \;

# Set up clean collection copy for testuser before running any tests
echo "Setting up clean collection copy for testuser..."
test_user_home=$(getent passwd testuser | cut -d: -f6)
test_user_gid=$(getent passwd testuser | cut -d: -f4)
test_user_group=$(getent group "${test_user_gid}" | cut -d: -f1)
test_dir="${test_user_home}/.ansible/collections/" \
	"ansible_collections/o0_o/posix"
mkdir -p "${test_dir}"
# Copy everything except .venv (which has hardcoded paths to /root)
rsync -a --exclude='.venv' . "${test_dir}/"
chown -R testuser:"${test_user_group}" "${test_user_home}/.ansible"

# Source the venv
. .venv/bin/activate

# Install specific Ansible version if provided
if [ -n "${ANSIBLE_PACKAGE:-}" ]; then
	pip install --upgrade "${ANSIBLE_PACKAGE}"
	echo "Installed Ansible version:"
	ansible --version
fi

# Build the test command
if [ -n "$INTEGRATION_TARGET" ]; then
	test_cmd="ansible-test ${TEST_TYPE} --venv --python ${PYTHON_VERSION} " \
		"${INTEGRATION_TARGET} -vvv"
	echo "Running ${TEST_TYPE} tests for target '${INTEGRATION_TARGET}' " \
		"as root user..."
else
	test_cmd="ansible-test ${TEST_TYPE} --venv --python ${PYTHON_VERSION} -vvv"
	echo "Running ${TEST_TYPE} tests as root user..."
fi

${test_cmd}

# Run tests as non-root user
if [ -n "$INTEGRATION_TARGET" ]; then
	echo "Running ${TEST_TYPE} tests for target '${INTEGRATION_TARGET}' " \
		"as non-root user..."
	testuser_cmd="ansible-test ${TEST_TYPE} --venv --python ${PYTHON_VERSION} " \
		"${INTEGRATION_TARGET} -vvv"
else
	echo "Running ${TEST_TYPE} tests as non-root user..."
	testuser_cmd="ansible-test ${TEST_TYPE} --venv " \
		"--python ${PYTHON_VERSION} -vvv"
fi

# Change to a neutral directory first to avoid pyenv trying to access /root
cd /tmp
echo "Setting up pyenv and venv for testuser..."
su testuser -c "
	set -eux
	umask 002
	export PATH=\$HOME/.local/bin:/opt/pyenv/shims:/opt/pyenv/bin:\$PATH
	cd ~/.ansible/collections/ansible_collections/o0_o/posix
	python -m venv .venv
	. .venv/bin/activate
	pip install --quiet --upgrade pip
	if [ -n '${ANSIBLE_PACKAGE:-}' ]; then
		pip install --quiet '${ANSIBLE_PACKAGE}'
	else
		pip install --quiet ansible-core
	fi
	echo 'Installed Ansible version:'
	ansible --version
	${testuser_cmd}
"
