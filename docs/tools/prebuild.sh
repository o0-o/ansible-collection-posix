#!/usr/bin/env bash
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later
# (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
#
# Copyright (c) 2025 oØ.o (@o0-o)
#
# This file is part of the o0_o.posix Ansible Collection.

set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
SOURCE_DIR="${REPO_ROOT}/docs/source"
GENERATED_DIR="${SOURCE_DIR}/generated"
TEMP_COLLECTION_ROOT=$(mktemp -d)

cleanup() {
    popd >/dev/null
    rm -rf "${TEMP_COLLECTION_ROOT}"
}

rm -rf "${GENERATED_DIR}"
mkdir -p "${GENERATED_DIR}"
chmod og-w "${GENERATED_DIR}"

pushd "${SOURCE_DIR}" >/dev/null
trap cleanup EXIT

mkdir -p "${TEMP_COLLECTION_ROOT}/ansible_collections/o0_o"
ln -s "${REPO_ROOT}" "${TEMP_COLLECTION_ROOT}/ansible_collections/o0_o/posix"
export ANSIBLE_COLLECTIONS_PATHS="${TEMP_COLLECTION_ROOT}:${ANSIBLE_COLLECTIONS_PATHS:-}"

antsibull-docs \
    --config-file "${SOURCE_DIR}/antsibull-docs.cfg" \
    collection \
    --cleanup everything \
    --use-current \
    --squash-hierarchy \
    --dest-dir "${GENERATED_DIR}" \
    o0_o.posix
