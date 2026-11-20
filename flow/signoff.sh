#!/usr/bin/env bash
# ==============================================================================
# Stage 4: MPW Sign-Off (Precheck / DRC / Strict LVS / MDP / IP62 DRC / STA)
# ==============================================================================
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_tool "klayout" "${KLAYOUT_BIN}"
require_tool "openroad" "${OPENROAD_BIN}"

SUB_GDS="output/gds/${DESIGN_TOP_CELL}.gds"
SUB_CIR="output/gds/${DESIGN_TOP_CELL}.cir"
SUB_EXT="${DESIGN_TOP_CELL}.extracted"
DRC_RPT="${REPO_ROOT}/output/reports/drc.lyrdb"
LVS_RPT="${REPO_ROOT}/output/reports/lvs.lvsdb"
MDP_GDS="output/gds/${SIGNOFF_MDP_FILE}"
IP62_RPT="${REPO_ROOT}/output/reports/ip62_drc.lyrdb"
STA_RPT="output/reports/sta.rpt"

# 1. MPW Precheck
if [[ "${SIGNOFF_PRECHECK}" == "true" ]]; then
    echo "=== [1/6] MPW Precheck ==="
    "${KLAYOUT_BIN}" -b -r scripts/pre_check.py \
        -rd input="${REPO_ROOT}/${SUB_GDS}" \
        -rd top_cell="${DESIGN_TOP_CELL}" 2>&1 | tee output/logs/precheck.log
fi

# 2. KLayout DRC
if [[ "${SIGNOFF_DRC}" == "true" ]]; then
    echo "=== [2/6] KLayout Full-Chip DRC ==="
    "${KLAYOUT_BIN}" -b -r "${PDK_DRC_DECK}" \
        -rd input="${REPO_ROOT}/${SUB_GDS}" \
        -rd top_cell="${DESIGN_TOP_CELL}" \
        -rd report="${DRC_RPT}" 2>&1 | tee output/logs/drc.log
    if grep -q "<visited>false</visited>" "${DRC_RPT}"; then
        echo "ERROR: KLayout DRC violations found in ${DRC_RPT}" >&2
        exit 1
    fi
fi

# 3. KLayout LVS (strict port mode)
if [[ "${SIGNOFF_LVS_ENABLED}" == "true" ]]; then
    echo "=== [3/6] KLayout Full-Chip LVS ==="
    LVS_EXTRA=""
    if [[ "${SIGNOFF_LVS_NETLIST_ONLY}" == "true" ]]; then
        LVS_EXTRA="-rd netlist_only=true"
    fi
    "${KLAYOUT_BIN}" -b -r "${PDK_LVS_DECK}" \
        -rd input="${REPO_ROOT}/${SUB_GDS}" \
        -rd top_cell="${DESIGN_TOP_CELL}" \
        -rd circuit="${DESIGN_TOP_CELL}.cir" \
        -rd extracted="${SUB_EXT}" \
        -rd report="${LVS_RPT}" \
        ${LVS_EXTRA} 2>&1 | tee output/logs/lvs.log
    if grep -q "ERROR : Netlists don't match" output/logs/lvs.log; then
        echo "ERROR: KLayout LVS FAILED (netlists don't match)" >&2
        exit 1
    fi
fi

# 4. MDP & IP62 Mask DRC
if [[ "${SIGNOFF_MDP_ENABLED}" == "true" && -n "${PDK_MDP_DECK}" && -f "${PDK_MDP_DECK}" ]]; then
    echo "=== [4/6] KLayout MDP & IP62 Mask DRC ==="
    "${KLAYOUT_BIN}" -b -r "${PDK_MDP_DECK}" \
        -rd input="${REPO_ROOT}/${SUB_GDS}" \
        -rd top_cell="${DESIGN_TOP_CELL}" \
        -rd output="${REPO_ROOT}/${MDP_GDS}" 2>&1 | tee output/logs/mdp.log
    if [[ ! -f "${MDP_GDS}" ]]; then
        echo "ERROR: MDP output GDS not generated: ${MDP_GDS}" >&2
        exit 1
    fi
    if [[ -n "${PDK_IP62_DECK}" && -f "${PDK_IP62_DECK}" ]]; then
        "${KLAYOUT_BIN}" -b -r "${PDK_IP62_DECK}" \
            -rd input="${REPO_ROOT}/${MDP_GDS}" \
            -rd top_cell="${DESIGN_TOP_CELL}" \
            -rd report="${IP62_RPT}" 2>&1 | tee output/logs/ip62_drc.log
        if grep -q "<visited>false</visited>" "${IP62_RPT}"; then
            echo "ERROR: IP62 Mask DRC violations found in ${IP62_RPT}" >&2
            exit 1
        fi
    fi
fi

# 5. OpenROAD / OpenSTA Static Timing Analysis
if [[ "${SIGNOFF_STA_ENABLED}" == "true" ]]; then
    echo "=== [5/6] OpenROAD Static Timing Analysis (STA) ==="
    cat > output/work/run_sta.tcl <<EOF
read_lef "${REPO_ROOT}/${PDK_TECH_LEF}"
read_lef "${REPO_ROOT}/${PDK_DRT_CELLS_LEF}"
read_liberty "${REPO_ROOT}/${PDK_LIBERTY}"
read_verilog "${REPO_ROOT}/output/work/${DESIGN_TOP_MODULE}_gl.v"
link_design ${DESIGN_TOP_MODULE}
read_sdc "${REPO_ROOT}/${DESIGN_SDC}"
report_checks -path_delay max -fields {slew cap input_pins fanout} -digits 3
report_checks -path_delay min -digits 3
report_tns -digits 3
report_wns -digits 3
report_worst_slack -max -digits 3
report_worst_slack -min -digits 3
exit
EOF
    "${OPENROAD_BIN}" -exit output/work/run_sta.tcl 2>&1 | tee "${STA_RPT}" output/logs/sta.log
fi

# 6. Build unified JSON summary for CI & Gemini/Vertex AI PPA loop
echo "=== [6/6] Generate Unified Sign-Off & PPA Summary ==="
python3 scripts/build_summary.py

echo "STAGE 4 (SIGNOFF) PASS"
