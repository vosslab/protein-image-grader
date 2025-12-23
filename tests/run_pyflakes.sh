#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if ! command -v pyflakes >/dev/null 2>&1; then
	echo "pyflakes not found, install it to run this check"
	exit 1
fi

PY_FILES=$(find "${REPO_ROOT}" \
	-path "${REPO_ROOT}/Protein_Images_Archive_Content" -prune -o \
	-path "${REPO_ROOT}/archive" -prune -o \
	-path "${REPO_ROOT}/data/runs" -prune -o \
	-type f -name "*.py" -print)

pyflakes ${PY_FILES}
