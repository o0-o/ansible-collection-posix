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

set -e  # Exit on any command failure

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

# Create and activate venv for root user
echo "Setting up Python environment for root user..."
cd /root
python -m venv .venv
. .venv/bin/activate
pip install --quiet --upgrade pip

# Install specific Ansible version if provided
if [ -n "${ANSIBLE_PACKAGE:-}" ]; then
	pip install --upgrade "${ANSIBLE_PACKAGE}"
	echo "Installed Ansible version:"
	ansible --version
fi

# Install collection from built tarball with dependencies
ansible-galaxy collection install /build/o0_o-posix-*.tar.gz --force -p /root/.ansible/collections -vvv

# Navigate to installed collection for running tests
cd /root/.ansible/collections/ansible_collections/o0_o/posix

# Build the test command
if [ -n "$INTEGRATION_TARGET" ]; then
	test_cmd="ansible-test ${TEST_TYPE} --venv --python ${PYTHON_VERSION}"
	test_cmd="${test_cmd} ${INTEGRATION_TARGET} -vvv"
	echo "Running ${TEST_TYPE} tests for target '${INTEGRATION_TARGET}' " \
		"as root user..."
else
	test_cmd="ansible-test ${TEST_TYPE} --venv --python ${PYTHON_VERSION}"
	test_cmd="${test_cmd} -vvv"
	echo "Running ${TEST_TYPE} tests as root user..."
fi

${test_cmd}

# Run tests as non-root user
testuser_cmd=""
if [ -n "$INTEGRATION_TARGET" ]; then
	echo "Running ${TEST_TYPE} tests for target '${INTEGRATION_TARGET}' " \
		"as non-root user..."
	testuser_cmd="ansible-test ${TEST_TYPE} --venv --python"
	testuser_cmd="${testuser_cmd} ${PYTHON_VERSION} ${INTEGRATION_TARGET}"
	testuser_cmd="${testuser_cmd} -vvv"
else
	echo "Running ${TEST_TYPE} tests as non-root user..."
	testuser_cmd="ansible-test ${TEST_TYPE} --venv --python"
	testuser_cmd="${testuser_cmd} ${PYTHON_VERSION} -vvv"
fi

echo "Setting up pyenv and venv for testuser..."
su testuser -c "
	set -eux
	umask 002
	export PATH=\$HOME/.local/bin:/opt/pyenv/shims:/opt/pyenv/bin:\$PATH
	cd ~
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
	# Install collection from built tarball with dependencies
	ansible-galaxy collection install /build/o0_o-posix-*.tar.gz --force -p ~/.ansible/collections -vvv
	# Navigate to installed collection
	cd ~/.ansible/collections/ansible_collections/o0_o/posix
	${testuser_cmd}
"
