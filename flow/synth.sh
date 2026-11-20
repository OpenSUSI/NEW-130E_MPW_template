#!/usr/bin/env bash
# ==============================================================================
# Stage 1: Validate + RTL Simulation + Yosys Synthesis + Gate-Level Simulation
# ==============================================================================
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_tool "iverilog" "${IVERILOG_BIN}"
require_tool "vvp" "${VVP_BIN}"
require_tool "yosys" "${YOSYS_BIN}"

echo "=== [1/4] Template & Schema Pre-Validation ==="
python3 scripts/validate.py --stage pre

echo "=== [2/4] RTL Simulation (${DESIGN_TESTBENCH}) ==="
"${IVERILOG_BIN}" -g2005 -o output/work/sim_rtl.vvp ${DESIGN_RTL_FILES} "${DESIGN_TESTBENCH}"
"${VVP_BIN}" output/work/sim_rtl.vvp | tee output/logs/rtl_sim.log
grep -q "PASS:" output/logs/rtl_sim.log

echo "=== [3/4] Yosys Synthesis (PDK=${PDK_NAME}, top=${DESIGN_TOP_MODULE}) ==="
DONT_USE_FLAGS=""
for cell in ${PDK_DONT_USE_CELLS}; do
    DONT_USE_FLAGS="${DONT_USE_FLAGS} -dont_use ${cell}"
done

TECHMAP_CMD="techmap"
for cand in "/usr/local/share/yosys/techmap.v" "/opt/homebrew/share/yosys/techmap.v" "/usr/share/yosys/techmap.v"; do
    if [[ -f "${cand}" ]]; then
        TECHMAP_CMD="techmap -map ${cand}"
        break
    fi
done

YOSYS_SCRIPT="output/work/synth.ys"
cat > "${YOSYS_SCRIPT}" <<EOF
# Auto-generated Yosys synthesis script (PDK: ${PDK_NAME})
read_liberty -lib ${PDK_LIBERTY}
read_verilog ${DESIGN_RTL_FILES}
hierarchy -check -top ${DESIGN_TOP_MODULE}

proc; opt -full; memory; opt -full
wreduce; peepopt; opt_clean
${TECHMAP_CMD}; opt -full
EOF

if [[ "${PDK_FLOW_DRIVER}" == "tr1um_2m" ]]; then
    echo 'dfflegalize -cell $_DFFE_PN0P_ 01 -cell $_DFFE_PN0N_ 01 -cell $_DFF_PN0_ 01' >> "${YOSYS_SCRIPT}"
fi

if [[ -n "${PDK_DFFE_MAP}" && -f "${PDK_DFFE_MAP}" ]]; then
    echo "techmap -map ${PDK_DFFE_MAP}" >> "${YOSYS_SCRIPT}"
fi

cat >> "${YOSYS_SCRIPT}" <<EOF
dfflibmap -liberty ${PDK_LIBERTY}
opt -full
abc -liberty ${PDK_LIBERTY} ${DONT_USE_FLAGS}
opt_clean -purge
EOF

if [[ -n "${PDK_TIE_HI_CELL}" && -n "${PDK_TIE_LO_CELL}" ]]; then
    cat >> "${YOSYS_SCRIPT}" <<EOF
hilomap -hicell ${PDK_TIE_HI_CELL} ${PDK_TIE_HI_PIN} -locell ${PDK_TIE_LO_CELL} ${PDK_TIE_LO_PIN}
EOF
fi

if [[ -n "${PDK_BUFFER_CELL}" ]]; then
    cat >> "${YOSYS_SCRIPT}" <<EOF
insbuf -buf ${PDK_BUFFER_CELL} ${PDK_BUFFER_IN_PIN} ${PDK_BUFFER_OUT_PIN}
opt_clean -purge
EOF
fi

cat >> "${YOSYS_SCRIPT}" <<EOF
# Bus-port gate-level netlist for testbench simulation
write_verilog -noattr -noexpr -nohex output/work/${DESIGN_TOP_MODULE}_gl.v

# Split vector ports for flat OpenROAD DEF & LVS SPICE matching
splitnets -ports
opt_clean -purge

stat -liberty ${PDK_LIBERTY}
tee -q -o output/reports/synth_stats.json stat -json -liberty ${PDK_LIBERTY}
write_verilog -noattr -noexpr -nohex output/work/${DESIGN_TOP_MODULE}_syn.v
EOF

"${YOSYS_BIN}" -s "${YOSYS_SCRIPT}" 2>&1 | tee output/logs/synth.log

echo "=== [4/4] Gate-Level Simulation (Post-Synthesis) ==="
GL_EXTRA_FLAGS=()
if [[ "${PDK_FLOW_DRIVER}" != "tr1um_2m" ]]; then
    GL_EXTRA_FLAGS+=("-DFUNCTIONAL" "-DUNIT_DELAY=#1")
fi
GL_MODELS=()
for vf in ${PDK_VERILOG_MODELS:-${PDK_PRIMITIVES_V}}; do
    if [[ -f "${vf}" ]]; then
        GL_MODELS+=("${vf}")
    fi
done
"${IVERILOG_BIN}" -g2005 -DGATE_LEVEL "${GL_EXTRA_FLAGS[@]}" -o output/work/sim_gl.vvp \
    "${GL_MODELS[@]}" \
    "output/work/${DESIGN_TOP_MODULE}_gl.v" \
    "${DESIGN_TESTBENCH}"
"${VVP_BIN}" output/work/sim_gl.vvp | tee output/logs/gl_sim.log
grep -q "PASS:" output/logs/gl_sim.log

echo "STAGE 1 (SYNTH) PASS"
