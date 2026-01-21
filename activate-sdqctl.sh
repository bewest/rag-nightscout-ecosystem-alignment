#!/bin/bash
# Activate venv and add sdqctl to PYTHONPATH
# Usage: source activate-sdqctl.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SDQCTL_DIR="${SCRIPT_DIR}/../copilot-do-proposal/sdqctl"

# Activate the venv
source "${SCRIPT_DIR}/.venv/bin/activate"

# Add sdqctl to PYTHONPATH and PATH
export PYTHONPATH="${SDQCTL_DIR}:${PYTHONPATH}"
export PATH="${SDQCTL_DIR}/bin:${PATH}"

echo "Activated venv with sdqctl from ${SDQCTL_DIR}"
