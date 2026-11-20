#!/usr/bin/env bash
# ==============================================================================
# Stage 2: Floorplan, Placement, TAP Insertion, and Active Decap Fill
# ==============================================================================
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

echo "=== Stage 2: Floorplan & Placement (driver=${PDK_FLOW_DRIVER}) ==="

case "${PDK_FLOW_DRIVER}" in
    tr1um_2m)
        python3 scripts/tr1um_place.py 2>&1 | tee output/logs/floorplan.log
        ;;
    *)
        echo "ERROR: Unsupported flow_driver '${PDK_FLOW_DRIVER}'. Implement driver for ${PDK_NAME}." >&2
        exit 1
        ;;
esac

echo "STAGE 2 (FLOORPLAN) PASS"
