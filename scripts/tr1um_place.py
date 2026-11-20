#!/usr/bin/env python3
"""
Generic TR-1um 2-Metal (M1/M2) Floorplanner, Placer, and Active Decap Filler.
Reads synthesized Verilog netlist, design.yaml, pdk/tr1um/pdk.yaml, and
constraints/pin_order.cfg to produce a legalized OpenROAD placement DEF
with 11 rows x 3 segments (4 TAP2 columns) and FILL3/FILL2 decap fill (FILL1=0).
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from config_loader import load_design_and_pdk, parse_pin_order

DBU = 1000
SITE_W = 5.4
ROW_H = 59.4
NUM_ROWS = 11
ROW_PITCH = 145.8
ROW_YS = [round(27.0 + r * ROW_PITCH, 4) for r in range(NUM_ROWS)]

TAP_XS = [21.6, 615.6, 1215.0, 1809.0]
SEGMENTS = [
    (32.4, 615.6, 108),    # Seg 0 (West)
    (626.4, 1215.0, 109),  # Seg 1 (Center)
    (1225.8, 1809.0, 108), # Seg 2 (East)
]

# Physical OSS_FRAME_GIO signal pad geometry in Core coordinates (um):
#   pad -> (edge, pad_in_coord, out_coord, hiz_coord, core_pin_in_xy, core_pin_out_xy)
# For N/S edges: coord is X (um), core pin is METAL2 (x1, y1, x2, y2).
# For W/E edges: coord is Y (um), core pin is METAL1 (x1, y1, x2, y2) in inter-row channel.
TR1UM_PAD_GEOM = {
    # North edge (y = 1840.0)
    "P2":  ("N", 390.0,  300.0,  340.0,  ("METAL2", 388.3, 1795.0, 391.7, 1815.0), ("METAL2", 298.3, 1795.0, 301.7, 1815.0)),
    "P1":  ("N", 650.0,  740.0,  700.0,  ("METAL2", 648.3, 1795.0, 651.7, 1815.0), ("METAL2", 738.3, 1795.0, 741.7, 1815.0)),
    "P15": ("N", 1450.0, 1540.0, 1500.0, ("METAL2", 1448.3, 1795.0, 1451.7, 1815.0), ("METAL2", 1538.3, 1795.0, 1541.7, 1815.0)),
    # South edge (y = 0.0)
    "P7":  ("S", 390.0,  300.0,  340.0,  ("METAL2", 388.3, 16.0,   391.7, 25.0),   ("METAL2", 298.3, 16.0,   301.7, 25.0)),
    "P9":  ("S", 1190.0, 1100.0, 1140.0, ("METAL2", 1188.3, 16.0,  1191.7, 25.0),  ("METAL2", 1098.3, 16.0,  1101.7, 25.0)),
    "P10": ("S", 1450.0, 1540.0, 1500.0, ("METAL2", 1448.3, 16.0,  1451.7, 25.0),  ("METAL2", 1538.3, 16.0,  1541.7, 25.0)),
    # West edge (x = 0.0) — channel-aligned Y coordinates
    "P6":  ("W", 390.0,  300.0,  340.0,  ("METAL1", 37.0, 422.9,  47.0, 424.9),  ("METAL1", 37.0, 304.1,  47.0, 306.1)),
    "P5":  ("W", 650.0,  740.0,  700.0,  ("METAL1", 37.0, 698.3,  47.0, 700.3),  ("METAL1", 37.0, 730.7,  47.0, 732.7)),
    "P4":  ("W", 1190.0, 1100.0, 1140.0, ("METAL1", 37.0, 1162.7, 47.0, 1164.7), ("METAL1", 37.0, 1124.9, 47.0, 1126.9)),
    "P3":  ("W", 1450.0, 1540.0, 1500.0, ("METAL1", 37.0, 1421.9, 47.0, 1423.9), ("METAL1", 37.0, 1567.7, 47.0, 1569.7)),
    # East edge (x = 1840.0) — channel-aligned Y coordinates
    "P11": ("E", 390.0,  300.0,  340.0,  ("METAL1", 1793.0, 422.9,  1803.0, 424.9),  ("METAL1", 1793.0, 304.1,  1803.0, 306.1)),
    "P12": ("E", 650.0,  740.0,  700.0,  ("METAL1", 1793.0, 698.3,  1803.0, 700.3),  ("METAL1", 1793.0, 730.7,  1803.0, 732.7)),
    "P13": ("E", 1190.0, 1100.0, 1140.0, ("METAL1", 1793.0, 1162.7, 1803.0, 1164.7), ("METAL1", 1793.0, 1124.9, 1803.0, 1126.9)),
    "P14": ("E", 1450.0, 1540.0, 1500.0, ("METAL1", 1793.0, 1421.9, 1803.0, 1423.9), ("METAL1", 1793.0, 1567.7, 1803.0, 1569.7)),
}


def clean_ident(name: str) -> str:
    s = name.strip()
    if s.startswith("\\"):
        s = s[1:]
    return s.strip()


def def_escape(name: str) -> str:
    """Escape net/instance names for OpenROAD DEF."""
    return name


def parse_gate_verilog(v_path: Path) -> tuple[list[tuple[str, str, dict[str, str]]], dict[str, list[tuple[str, str]]]]:
    """
    Parse Yosys gate-level Verilog (-noattr -noexpr -nohex, splitnets -ports).
    Returns:
      instances: [(cell_type, inst_name, {pin: net})]
      nets: {net_name: [(inst_name, pin_name)]}
    """
    text = v_path.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//.*", "", text)

    # Join statements separated by ';'
    stmts = [s.strip() for s in text.split(";") if s.strip()]
    instances: list[tuple[str, str, dict[str, str]]] = []
    nets: dict[str, list[tuple[str, str]]] = defaultdict(list)

    skip_kw = ("module", "endmodule", "input", "output", "inout", "wire", "reg", "assign")
    inst_re = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s+(\\?\S+)\s*\((.*)\)$", re.DOTALL)
    port_re = re.compile(r"\.([A-Za-z0-9_]+)\s*\(\s*([^)]+?)\s*\)")

    for st in stmts:
        first_tok = st.split()[0] if st.split() else ""
        if first_tok in skip_kw or st.startswith("endmodule"):
            continue
        m = inst_re.match(st)
        if not m:
            continue
        cell_type = m.group(1)
        inst_name = clean_ident(m.group(2))
        ports_str = m.group(3)
        pmap: dict[str, str] = {}
        for pm in port_re.finditer(ports_str):
            pin = pm.group(1)
            net = clean_ident(pm.group(2))
            if net in ("", "1'b0", "1'b1", "1'h0", "1'h1"):
                continue
            pmap[pin] = net
            nets[net].append((inst_name, pin))
        instances.append((cell_type, inst_name, pmap))

    return instances, nets


def fill_gap_no_fill1(gap_sites: int) -> list[str]:
    """Decompose gap_sites >= 2 into FILL3 and FILL2 (never FILL1)."""
    if gap_sites == 0:
        return []
    if gap_sites == 1:
        raise ValueError("Cannot fill a 1-site gap without FILL1")
    rem = gap_sites % 3
    if rem == 0:
        return ["FILL3"] * (gap_sites // 3)
    elif rem == 2:
        return ["FILL3"] * (gap_sites // 3) + ["FILL2"]
    else:  # rem == 1 -> gap_sites >= 4
        return ["FILL3"] * ((gap_sites - 4) // 3) + ["FILL2", "FILL2"]


def main() -> None:
    design, pdk = load_design_and_pdk(ROOT)
    top_module = design["design"]["top_module"]
    pin_cfg_path = ROOT / design["design"]["constraints"]["pin_order"]
    syn_v_path = ROOT / "output/work" / f"{top_module}_syn.v"
    cell_info_path = ROOT / pdk["views"]["cell_info_json"]
    out_def_path = ROOT / "output/work" / f"{top_module}_placed.def"
    out_rpt_path = ROOT / "output/reports/floorplan.json"

    cell_info = json.loads(cell_info_path.read_text(encoding="utf-8"))
    pin_entries = parse_pin_order(pin_cfg_path)
    instances, nets = parse_gate_verilog(syn_v_path)

    if not instances:
        raise RuntimeError(f"No standard cell instances parsed from {syn_v_path}")

    # Build core pins from pin_order.cfg
    core_pins: list[tuple[str, str, str, float, float, float, float]] = []
    pin_centers: dict[str, tuple[float, float]] = {}
    for e in pin_entries:
        if e["direction"] not in ("IN", "OUT"):
            continue
        pad = e["pad"]
        sig = e["signal"]
        direction = "INPUT" if e["direction"] == "IN" else "OUTPUT"
        _, _, _, _, in_pin, out_pin = TR1UM_PAD_GEOM[pad]
        layer, x1, y1, x2, y2 = in_pin if direction == "INPUT" else out_pin
        core_pins.append((sig, direction, layer, x1, y1, x2, y2))
        pin_centers[sig] = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    # Compute initial target (x, y) for each instance via iterative barycenter relaxation
    inst_pos: dict[str, tuple[float, float]] = {inst: (920.0, 820.0) for _, inst, _ in instances}
    inst_nets: dict[str, list[str]] = {inst: list(pmap.values()) for _, inst, pmap in instances}

    for _ in range(12):
        new_pos: dict[str, tuple[float, float]] = {}
        for _, inst, _ in instances:
            xs, ys = [], []
            for net in inst_nets[inst]:
                if net in pin_centers:
                    px, py = pin_centers[net]
                    # Stronger weight to I/O pins
                    xs.extend([px, px])
                    ys.extend([py, py])
                for other_inst, _ in nets.get(net, []):
                    if other_inst != inst and other_inst in inst_pos:
                        ox, oy = inst_pos[other_inst]
                        xs.append(ox)
                        ys.append(oy)
            if xs:
                new_pos[inst] = (sum(xs) / len(xs), sum(ys) / len(ys))
            else:
                new_pos[inst] = inst_pos[inst]
        inst_pos = new_pos

    # Assign instances to (row, seg) slots with capacity check and leaving >= 2 sites spare
    # so FILL3/FILL2 never encounters a 1-site gap.
    inst_sites: dict[str, int] = {}
    for ctype, inst, _ in instances:
        if ctype not in cell_info:
            raise KeyError(f"Cell '{ctype}' missing from {cell_info_path}")
        inst_sites[inst] = int(round(cell_info[ctype]["sites"]))

    seg_cells: dict[tuple[int, int], list[tuple[str, str, int, float]]] = defaultdict(list)
    seg_used: dict[tuple[int, int], int] = defaultdict(int)

    # Sort larger cells first for clean bin packing
    ordered_insts = sorted(instances, key=lambda x: (-inst_sites[x[1]], inst_pos[x[1]][1], inst_pos[x[1]][0]))

    for ctype, inst, _ in ordered_insts:
        tx, ty = inst_pos[inst]
        w_sites = inst_sites[inst]

        # Rank all (row, seg) candidates by Manhattan distance from target (tx, ty)
        cands = []
        for r, ry in enumerate(ROW_YS):
            rcy = ry + ROW_H / 2.0
            for s_idx, (sx1, sx2, cap) in enumerate(SEGMENTS):
                scx = (sx1 + sx2) / 2.0
                used = seg_used[(r, s_idx)]
                # Keep at least 9 spare sites per segment if possible, or >=2 minimum
                if used + w_sites <= cap - 2:
                    dist = abs(tx - scx) + abs(ty - rcy)
                    cands.append((dist + used * 2.0, r, s_idx))
        if not cands:
            raise RuntimeError(f"Design exceeds TR-1um 11-row core capacity while placing {inst} ({ctype})")
        cands.sort()
        _, best_r, best_s = cands[0]
        seg_cells[(best_r, best_s)].append((ctype, inst, w_sites, tx))
        seg_used[(best_r, best_s)] += w_sites

    # Legalize cells within each (row, seg), centering around their target X while avoiding 1-site gaps
    placed_components: list[tuple[str, str, int, int, str]] = []
    tap_count = 0
    fill3_count = 0
    fill2_count = 0
    logic_sites = sum(inst_sites.values())
    total_sites = NUM_ROWS * sum(cap for _, _, cap in SEGMENTS)

    for r, ry in enumerate(ROW_YS):
        ry_dbu = int(round(ry * DBU))
        # 4 TAP2 columns per row
        for c_idx, tx in enumerate(TAP_XS):
            placed_components.append((f"TAP_R{r}_C{c_idx}", "TAP2", int(round(tx * DBU)), ry_dbu, "N"))
            tap_count += 1

        for s_idx, (sx1, sx2, cap) in enumerate(SEGMENTS):
            items = sorted(seg_cells.get((r, s_idx), []), key=lambda x: x[3])
            used = sum(it[2] for it in items)
            spare = cap - used
            if spare == 1:
                raise RuntimeError(f"Unexpected 1-site spare in row {r} seg {s_idx}")

            # Distribute leading filler so logic sits near segment barycenter (and always >= 0 and != 1)
            if items and spare >= 4:
                avg_tx = sum(it[3] for it in items) / len(items)
                desired_start = int(round((avg_tx - sx1) / SITE_W - used / 2.0))
                lead = max(0, min(spare, desired_start))
                if lead == 1:
                    lead = 2
                if spare - lead == 1:
                    lead = max(0, lead - 2) if lead >= 2 else 0
            else:
                lead = 0
            trail = spare - lead

            cur_site = 0
            fill_idx = 0
            for ftype in fill_gap_no_fill1(lead):
                fw = 3 if ftype == "FILL3" else 2
                fx = int(round((sx1 + cur_site * SITE_W) * DBU))
                placed_components.append((f"FILL_R{r}_S{s_idx}_{fill_idx}", ftype, fx, ry_dbu, "N"))
                fill_idx += 1
                if ftype == "FILL3":
                    fill3_count += 1
                else:
                    fill2_count += 1
                cur_site += fw

            for ctype, inst, w_sites, _ in items:
                cx = int(round((sx1 + cur_site * SITE_W) * DBU))
                placed_components.append((inst, ctype, cx, ry_dbu, "N"))
                cur_site += w_sites

            for ftype in fill_gap_no_fill1(trail):
                fw = 3 if ftype == "FILL3" else 2
                fx = int(round((sx1 + cur_site * SITE_W) * DBU))
                placed_components.append((f"FILL_R{r}_S{s_idx}_{fill_idx}", ftype, fx, ry_dbu, "N"))
                fill_idx += 1
                if ftype == "FILL3":
                    fill3_count += 1
                else:
                    fill2_count += 1
                cur_site += fw

            assert cur_site == cap, f"Row {r} Seg {s_idx}: filled {cur_site} != {cap}"

    # Write OpenROAD DEF
    out_def_path.parent.mkdir(parents=True, exist_ok=True)
    out_rpt_path.parent.mkdir(parents=True, exist_ok=True)

    die_w_dbu = int(round(float(pdk["geometry"]["core_width_um"]) * DBU))
    die_h_dbu = int(round(float(pdk["geometry"]["core_height_um"]) * DBU))
    pitch_dbu = int(round(SITE_W * DBU))
    offset_dbu = int(round(2.7 * DBU))
    num_tracks_x = (die_w_dbu - offset_dbu) // pitch_dbu
    num_tracks_y = (die_h_dbu - offset_dbu) // pitch_dbu

    lines: list[str] = [
        "VERSION 5.8 ;",
        'DIVIDERCHAR "/" ;',
        'BUSBITCHARS "[]" ;',
        f"DESIGN {top_module} ;",
        f"UNITS DISTANCE MICRONS {DBU} ;",
        f"DIEAREA ( 0 0 ) ( {die_w_dbu} {die_h_dbu} ) ;",
        "",
    ]

    for r, ry in enumerate(ROW_YS):
        ry_dbu = int(round(ry * DBU))
        x_start = int(round(TAP_XS[0] * DBU))
        # Total sites across 4 TAP2 (8 sites) + 3 segments (325 sites) = 333 sites
        lines.append(f"ROW ROW_{r} TR1UM {x_start} {ry_dbu} N DO 333 BY 1 STEP {pitch_dbu} 0 ;")
    lines.append("")
    lines.append(f"TRACKS X {offset_dbu} DO {num_tracks_x} STEP {pitch_dbu} LAYER METAL1 ;")
    lines.append(f"TRACKS Y {offset_dbu} DO {num_tracks_y} STEP {pitch_dbu} LAYER METAL1 ;")
    lines.append(f"TRACKS X {offset_dbu} DO {num_tracks_x} STEP {pitch_dbu} LAYER METAL2 ;")
    lines.append(f"TRACKS Y {offset_dbu} DO {num_tracks_y} STEP {pitch_dbu} LAYER METAL2 ;")
    lines.append("")

    lines.append(f"COMPONENTS {len(placed_components)} ;")
    for inst_name, ctype, x, y, orient in placed_components:
        lines.append(f"  - {def_escape(inst_name)} {ctype} + FIXED ( {x} {y} ) {orient} ;")
    lines.append("END COMPONENTS")
    lines.append("")

    lines.append(f"PINS {len(core_pins)} ;")
    for pname, direction, layer, x1, y1, x2, y2 in core_pins:
        px = int(round(((x1 + x2) / 2.0) * DBU))
        py = int(round(((y1 + y2) / 2.0) * DBU))
        rx1 = int(round((x1 - (x1 + x2) / 2.0) * DBU))
        ry1 = int(round((y1 - (y1 + y2) / 2.0) * DBU))
        rx2 = int(round((x2 - (x1 + x2) / 2.0) * DBU))
        ry2 = int(round((y2 - (y1 + y2) / 2.0) * DBU))
        lines.append(f"  - {pname} + NET {pname} + DIRECTION {direction} + USE SIGNAL")
        lines.append(f"    + LAYER {layer} ( {rx1} {ry1} ) ( {rx2} {ry2} )")
        lines.append(f"    + FIXED ( {px} {py} ) N ;")
    lines.append("END PINS")
    lines.append("")

    # Routing blockages protecting the 4 TAP2 vertical M2 power straps,
    # West/East HIZ_VDD buses, and North/South M1 VDD rails
    blockages = [
        ("METAL2", 6000, 0, 9400, 1840000),         # West HIZ_VDD M2 bus
        ("METAL2", 22600, 0, 31400, 1840000),       # Col 0 TAP2 VDD/VSS M2 straps
        ("METAL2", 616600, 0, 625400, 1840000),     # Col 1 TAP2 VDD/VSS M2 straps
        ("METAL2", 1216000, 0, 1224800, 1840000),   # Col 2 TAP2 VDD/VSS M2 straps
        ("METAL2", 1810000, 0, 1818800, 1840000),   # Col 3 TAP2 VDD/VSS M2 straps
        ("METAL2", 1830600, 0, 1834000, 1840000),   # East HIZ_VDD M2 bus
        ("METAL1", 0, 1826000, 1840000, 1840000),   # North M1 VDD bus
        ("METAL1", 0, 0, 1840000, 14000),           # South M1 VDD bus & pad stubs
    ]
    lines.append(f"BLOCKAGES {len(blockages)} ;")
    for lay, bx1, by1, bx2, by2 in blockages:
        lines.append(f"  - LAYER {lay} RECT ( {bx1} {by1} ) ( {bx2} {by2} ) ;")
    lines.append("END BLOCKAGES")
    lines.append("")

    # Build NETS section (include pins + cell connections)
    pin_set = {p[0] for p in core_pins}
    all_net_names = sorted(set(nets.keys()) | pin_set)
    active_nets = []
    for net in all_net_names:
        conns = []
        if net in pin_set:
            conns.append(f"( PIN {net} )")
        for inst_name, pin_name in nets.get(net, []):
            conns.append(f"( {def_escape(inst_name)} {pin_name} )")
        if len(conns) >= 2:
            active_nets.append((net, conns))

    lines.append(f"NETS {len(active_nets)} ;")
    for net, conns in active_nets:
        lines.append(f"  - {net} " + " ".join(conns) + " ;")
    lines.append("END NETS")
    lines.append("")
    lines.append("END DESIGN")
    lines.append("")

    out_def_path.write_text("\n".join(lines), encoding="utf-8")

    ff_count = sum(1 for ct, _, _ in instances if "DFF" in ct)
    util_pct = round(100.0 * logic_sites / total_sites, 2)
    report = {
        "pdk": pdk["name"],
        "top_module": top_module,
        "stdcell_count": len(instances),
        "ff_count": ff_count,
        "comb_count": len(instances) - ff_count,
        "logic_sites": logic_sites,
        "total_sites": total_sites,
        "utilization_pct": util_pct,
        "tap2_count": tap_count,
        "fill3_count": fill3_count,
        "fill2_count": fill2_count,
        "fill1_count": 0,
        "pin_count": len(core_pins),
        "net_count": len(active_nets),
        "placed_def": str(out_def_path.relative_to(ROOT)),
    }
    out_rpt_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(
        f"FLOORPLAN OK: {len(instances)} stdcells ({ff_count} FFs), "
        f"util={util_pct:.2f}% ({logic_sites}/{total_sites} sites), "
        f"TAP2={tap_count}, FILL3={fill3_count}, FILL2={fill2_count}, FILL1=0 -> {out_def_path.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
