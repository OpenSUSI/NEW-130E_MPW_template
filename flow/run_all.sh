#!/usr/bin/env bash
# ==============================================================================
# Full End-to-End GitHub-to-Silicon Pipeline Runner
# ==============================================================================
set -euo pipefail

FLOW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${FLOW_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

echo "========================================================================"
echo " OpenSUSI x Google AI-Assisted Chip Design Platform — Full EDA Pipeline "
echo "========================================================================"

bash "${FLOW_DIR}/synth.sh"
bash "${FLOW_DIR}/floorplan.sh"
bash "${FLOW_DIR}/place_route.sh"
bash "${FLOW_DIR}/signoff.sh"

echo "=== Post-Signoff Validation & MPW Submission Packaging ==="
python3 scripts/validate.py --stage post
python3 scripts/package.py

echo "========================================================================"
echo " PIPELINE COMPLETED: PASS (see output/reports/summary.json)"
echo "========================================================================"
