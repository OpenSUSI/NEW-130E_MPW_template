#!/usr/bin/env bash
# ==============================================================================
# Stage 3: OpenROAD Global Route -> Guide Expansion -> Detailed Route -> GDS/CIR
# ==============================================================================
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_tool "openroad" "${OPENROAD_BIN}"
require_tool "klayout" "${KLAYOUT_BIN}"

PLACED_DEF="output/work/${DESIGN_TOP_MODULE}_placed.def"
ROUTED_DEF="output/work/${DESIGN_TOP_MODULE}_routed.def"
GUIDE_RAW="output/work/route.guide"
GUIDE_EXP="output/work/route_expanded.guide"
ROUTE_DRC="output/reports/openroad_route_drc.rpt"

echo "=== [1/4] OpenROAD Global Route ==="
cat > output/work/run_grt.tcl <<EOF
read_lef "${REPO_ROOT}/${PDK_TECH_LEF}"
read_lef "${REPO_ROOT}/${PDK_GRT_CELLS_LEF}"
read_def "${REPO_ROOT}/${PLACED_DEF}"
set_routing_layers -signal ${PDK_METAL_LAYERS}
global_route -guide_file "${REPO_ROOT}/${GUIDE_RAW}" -congestion_iterations 50 -allow_congestion -verbose
exit
EOF
"${OPENROAD_BIN}" -exit output/work/run_grt.tcl 2>&1 | tee output/logs/global_route.log

echo "=== [2/4] Routing Guide Expansion ==="
python3 - "${GUIDE_RAW}" "${GUIDE_EXP}" <<'PYEOF'
import re, sys
from pathlib import Path

in_p, out_p = Path(sys.argv[1]), Path(sys.argv[2])
PAD, MAX_C = 81000, 1840000
rect_re = re.compile(r"^(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(METAL[12])$")
out = []
for line in in_p.read_text(encoding="utf-8").splitlines():
    m = rect_re.match(line.strip())
    if m:
        x1, y1, x2, y2, lay = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), m.group(5)
        out.append(f"{max(0, x1-PAD)} {max(0, y1-PAD)} {min(MAX_C, x2+PAD)} {min(MAX_C, y2+PAD)} {lay}")
    else:
        out.append(line)
out_p.write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"Expanded routing guide -> {out_p} ({len(out)} lines)")
PYEOF

echo "=== [3/4] OpenROAD Detailed Route ==="
cat > output/work/run_drt.tcl <<EOF
read_lef "${REPO_ROOT}/${PDK_TECH_LEF}"
read_lef "${REPO_ROOT}/${PDK_DRT_CELLS_LEF}"
read_def "${REPO_ROOT}/${PLACED_DEF}"
read_guides "${REPO_ROOT}/${GUIDE_EXP}"
set_routing_layers -signal ${PDK_METAL_LAYERS}
detailed_route -output_drc "${REPO_ROOT}/${ROUTE_DRC}" -droute_end_iter 40 -verbose 1
write_def "${REPO_ROOT}/${ROUTED_DEF}"
exit
EOF
"${OPENROAD_BIN}" -exit output/work/run_drt.tcl 2>&1 | tee output/logs/detailed_route.log

if [[ -s "${ROUTE_DRC}" ]]; then
    echo "ERROR: OpenROAD detailed_route reported DRC violations in ${ROUTE_DRC}" >&2
    head -n 40 "${ROUTE_DRC}" >&2
    exit 1
fi

echo "=== [4/4] Full-Chip GDSII Assembly & LVS SPICE Generation ==="
case "${PDK_FLOW_DRIVER}" in
    tr1um_2m)
        "${KLAYOUT_BIN}" -b -r scripts/tr1um_def2gds.py 2>&1 | tee output/logs/def2gds.log
        python3 scripts/tr1um_v2spice.py 2>&1 | tee output/logs/v2spice.log
        ;;
    *)
        echo "ERROR: Unsupported flow_driver '${PDK_FLOW_DRIVER}'." >&2
        exit 1
        ;;
esac

echo "STAGE 3 (PLACE & ROUTE) PASS"
