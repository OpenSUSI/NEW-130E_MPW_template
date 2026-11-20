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
    openroad_std)
        require_tool "openroad" "${OPENROAD_BIN}"
        DIE_W="${PDK_DIE_WIDTH_UM}"
        DIE_H="${PDK_DIE_HEIGHT_UM}"
        M="${PDK_CORE_MARGIN_UM}"
        CORE_X2="$(python3 -c "print(f'{float(${DIE_W}) - float(${M}):.3f}')")"
        CORE_Y2="$(python3 -c "print(f'{float(${DIE_H}) - float(${M}):.3f}')")"

        FP_TCL="output/work/run_floorplan.tcl"
        cat > "${FP_TCL}" <<EOF
read_lef "${REPO_ROOT}/${PDK_TECH_LEF}"
read_lef "${REPO_ROOT}/${PDK_DRT_CELLS_LEF}"
read_liberty "${REPO_ROOT}/${PDK_LIBERTY}"
read_verilog "${REPO_ROOT}/output/work/${DESIGN_TOP_MODULE}_syn.v"
link_design ${DESIGN_TOP_MODULE}
read_sdc "${REPO_ROOT}/${DESIGN_SDC}"

initialize_floorplan -die_area "0 0 ${DIE_W} ${DIE_H}" -core_area "${M} ${M} ${CORE_X2} ${CORE_Y2}" -site ${PDK_SITE_NAME}
make_tracks
EOF
        if [[ -n "${PDK_PIN_HOR_LAYER}" && -n "${PDK_PIN_VER_LAYER}" ]]; then
            echo "place_pins -hor_layers ${PDK_PIN_HOR_LAYER} -ver_layers ${PDK_PIN_VER_LAYER}" >> "${FP_TCL}"
        fi
        if [[ -n "${PDK_TAP_CELL}" ]]; then
            TAP_CMD="tapcell -tapcell_master ${PDK_TAP_CELL} -distance ${PDK_TAP_DISTANCE_UM}"
            if [[ -n "${PDK_ENDCAP_CELL}" ]]; then
                TAP_CMD="${TAP_CMD} -endcap_master ${PDK_ENDCAP_CELL}"
            fi
            echo "${TAP_CMD}" >> "${FP_TCL}"
        fi
        cat >> "${FP_TCL}" <<EOF
global_placement -density ${PDK_PLACE_DENSITY}
detailed_placement
check_placement -verbose
EOF
        if [[ -n "${PDK_FILLER_CELLS}" ]]; then
            echo "filler_placement {${PDK_FILLER_CELLS}}" >> "${FP_TCL}"
        fi
        cat >> "${FP_TCL}" <<EOF
report_design_area
write_def "${REPO_ROOT}/output/work/${DESIGN_TOP_MODULE}_placed.def"
exit
EOF
        "${OPENROAD_BIN}" -exit "${FP_TCL}" 2>&1 | tee output/logs/floorplan.log

        python3 - <<'PYEOF'
import json, re
from pathlib import Path

stats_p = Path("output/reports/synth_stats.json")
fp_log = Path("output/logs/floorplan.log").read_text(errors="replace")
stdcells = 0
if stats_p.is_file():
    data = json.loads(stats_p.read_text(encoding="utf-8"))
    stdcells = int(data.get("design", {}).get("num_cells", 0))
util = 0.0
m = re.search(r"Design area\s+[\d.]+\s+u\^2\s+([\d.]+)%\s+utilization", fp_log)
if m:
    util = float(m.group(1))
out = {
    "driver": "openroad_std",
    "stdcell_count": stdcells,
    "utilization_pct": util,
}
Path("output/reports/floorplan.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
PYEOF
        ;;
    *)
        echo "ERROR: Unsupported flow_driver '${PDK_FLOW_DRIVER}'. Implement driver for ${PDK_NAME}." >&2
        exit 1
        ;;
esac

echo "STAGE 2 (FLOORPLAN) PASS"
