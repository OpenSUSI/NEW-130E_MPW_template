#!/usr/bin/env python3
"""
Generic KLayout Python script to assemble TR-1um full-chip GDSII from OpenROAD routed DEF.
Supports arbitrary IN / OUT / UNUSED pad configurations in constraints/pin_order.cfg.

Run with:
  klayout -b -r scripts/tr1um_def2gds.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pya

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from config_loader import load_design_and_pdk, parse_pin_order
from tr1um_place import TR1UM_PAD_GEOM

CORE_OFFSET_X = -920000
CORE_OFFSET_Y = -920000

# Top-level pad label positions in OSS_FRAME coordinates (nm)
PAD_LABEL_COORDS = {
    "P1":  (-200000,  1040000),
    "P2":  (-600000,  1040000),
    "P3":  (-1040000,  600000),
    "P4":  (-1040000,  200000),
    "P5":  (-1040000, -200000),
    "P6":  (-1040000, -600000),
    "P7":  (-600000, -1040000),
    "P8":  (-200000, -1040000),
    "P9":  (200000,  -1040000),
    "P10": (600000,  -1040000),
    "P11": (1040000,  -600000),
    "P12": (1040000,  -200000),
    "P13": (1040000,   200000),
    "P14": (1040000,   600000),
    "P15": (600000,   1040000),
    "P16": (200000,   1040000),
}


def add_box(cell, layer_idx, x1, y1, x2, y2):
    ax1, ax2 = sorted((int(round(x1)), int(round(x2))))
    ay1, ay2 = sorted((int(round(y1)), int(round(y2))))
    cell.shapes(layer_idx).insert(pya.Box(ax1, ay1, ax2, ay2))


def add_via1(cell, li_m1, li_v1, li_m2, vx, vy):
    vx, vy = int(round(vx)), int(round(vy))
    cell.shapes(li_m1).insert(pya.Box(vx - 1700, vy - 1700, vx + 1700, vy + 1700))
    cell.shapes(li_v1).insert(pya.Box(vx - 700, vy - 700, vx + 700, vy + 700))
    cell.shapes(li_m2).insert(pya.Box(vx - 1700, vy - 1700, vx + 1700, vy + 1700))


def parse_def(def_path: Path):
    text = def_path.read_text(encoding="utf-8")

    # 1. COMPONENTS
    comp_sec = text.split("COMPONENTS ")[1].split("END COMPONENTS")[0]
    components = []
    for line in comp_sec.splitlines():
        s = line.strip()
        if s.startswith("- "):
            parts = s.split()
            inst_name = parts[1]
            macro_name = parts[2]
            idx = parts.index("(")
            x = int(parts[idx + 1])
            y = int(parts[idx + 2])
            orient = parts[idx + 4]
            components.append((inst_name, macro_name, x, y, orient))

    # 2. PINS
    pins_sec = text.split("PINS ")[1].split("END PINS")[0]
    pins = []
    for pb in pins_sec.split("- ")[1:]:
        lines = [l.strip() for l in pb.strip().splitlines()]
        pname = lines[0].split()[0]
        layer, rect, fixed = None, None, None
        for l in lines:
            if l.startswith("+ LAYER"):
                parts = l.split()
                layer = parts[2]
                rect = (int(parts[4]), int(parts[5]), int(parts[8]), int(parts[9]))
            elif l.startswith("+ FIXED"):
                parts = l.split()
                fixed = (int(parts[3]), int(parts[4]))
        if layer and rect and fixed:
            pins.append((pname, layer, fixed[0] + rect[0], fixed[1] + rect[1], fixed[0] + rect[2], fixed[1] + rect[3]))

    # 3. NETS (routed geometries)
    nets_sec = text.split("NETS ")[1].split("END NETS")[0]
    m1_rects, m2_rects, v1_pts = [], [], []
    net_blocks = re.split(r"\n\s*-\s+", "\n" + nets_sec)[1:]
    for nb in net_blocks:
        for line in nb.splitlines():
            s = line.strip()
            if not (s.startswith("+ ROUTED") or s.startswith("NEW")):
                continue
            tokens = s.replace("+", "").replace("ROUTED", "").replace("NEW", "").replace(";", "").split()
            layer = tokens[0]
            idx = 1
            pts = []
            last_x, last_y = None, None
            while idx < len(tokens):
                if tokens[idx] == "(":
                    tx, ty = tokens[idx + 1], tokens[idx + 2]
                    x = last_x if tx == "*" else int(tx)
                    y = last_y if ty == "*" else int(ty)
                    last_x, last_y = x, y
                    if tokens[idx + 3] != ")":
                        ext = int(tokens[idx + 3])
                        idx += 5
                    else:
                        ext = None
                        idx += 4
                    pts.append((x, y, ext))
                else:
                    if last_x is not None:
                        v1_pts.append((last_x, last_y))
                    idx += 1
            hw = 1000 if layer == "METAL1" else 1700
            for i in range(len(pts) - 1):
                x1, y1, e1 = pts[i]
                x2, y2, e2 = pts[i + 1]
                ext1 = hw if e1 is None else e1
                ext2 = hw if e2 is None else e2
                if x1 == x2:
                    by1, by2 = (y1 - ext1, y2 + ext2) if y1 <= y2 else (y2 - ext2, y1 + ext1)
                    bx1, bx2 = x1 - hw, x1 + hw
                else:
                    bx1, bx2 = (x1 - ext1, x2 + ext2) if x1 <= x2 else (x2 - ext2, x1 + ext1)
                    by1, by2 = y1 - hw, y1 + hw
                if layer == "METAL1":
                    m1_rects.append((bx1, by1, bx2, by2))
                elif layer == "METAL2":
                    m2_rects.append((bx1, by1, bx2, by2))

    return components, pins, m1_rects, m2_rects, v1_pts


def build_core(core_cell, layout, stdcell_gds: Path, components, pins, m1_rects, m2_rects, v1_pts, pin_map, include_frame_bridges=True):
    li_m1 = layout.layer(13, 0)
    li_v1 = layout.layer(19, 0)
    li_m2 = layout.layer(20, 0)

    l_std = pya.Layout()
    l_std.read(str(stdcell_gds))
    copied_cells = {}

    def get_cell(macro_name):
        if macro_name in copied_cells:
            return copied_cells[macro_name]
        src_c = l_std.cell(macro_name)
        if src_c is None:
            raise RuntimeError(f"Cell '{macro_name}' not found in {stdcell_gds}")
        dst_c = layout.create_cell(macro_name)
        dst_c.copy_tree(src_c)
        copied_cells[macro_name] = dst_c
        return dst_c

    for _, macro_name, x, y, _ in components:
        c = get_cell(macro_name)
        core_cell.insert(pya.CellInstArray(c.cell_index(), pya.Trans(0, False, x, y)))

    for bx1, by1, bx2, by2 in m1_rects:
        add_box(core_cell, li_m1, bx1, by1, bx2, by2)
    for bx1, by1, bx2, by2 in m2_rects:
        add_box(core_cell, li_m2, bx1, by1, bx2, by2)
    for vx, vy in v1_pts:
        add_via1(core_cell, li_m1, li_v1, li_m2, vx, vy)
    for _, layer, bx1, by1, bx2, by2 in pins:
        add_box(core_cell, li_m1 if layer == "METAL1" else li_m2, bx1, by1, bx2, by2)

    # =========================================================================
    # Power Mesh (4 TAP2 Columns across 11 Rows: Row 0 bottom=27um, Row 10 top=1544.4um)
    # =========================================================================
    y_south_vss = -10000 if include_frame_bridges else 0
    y_north_vss = 1850000 if include_frame_bridges else 1840000
    x_west_vss = -10000 if include_frame_bridges else 0
    x_east_vss = 1850000 if include_frame_bridges else 1840000

    # Col 0 (West, tap_x = 21.6um): VSS=22.6..26.0, VDD=28.0..31.4
    add_box(core_cell, li_m2, 22600, y_south_vss, 26000, y_north_vss)
    add_box(core_cell, li_m2, 28000, 10000, 31400, 1834000)

    # Col 1 (Center-Left, tap_x = 615.6um): VSS=616.6..620.0, VDD=622.0..625.4
    add_box(core_cell, li_m2, 616600, y_south_vss, 620000, y_north_vss)
    add_box(core_cell, li_m2, 622000, 10000, 625400, 1834000)

    # Col 2 (Center-Right, tap_x = 1215.0um): VSS=1216.0..1219.4, VDD=1221.4..1224.8
    add_box(core_cell, li_m2, 1216000, y_south_vss, 1219400, y_north_vss)
    add_box(core_cell, li_m2, 1221400, 10000, 1224800, 1834000)

    # Col 3 (East, tap_x = 1809.0um): VSS=1810.0..1813.4, VDD=1815.4..1818.8
    add_box(core_cell, li_m2, 1810000, y_south_vss, 1813400, y_north_vss)
    add_box(core_cell, li_m2, 1815400, 10000, 1818800, 1834000)

    # Check whether West or East pads require HIZ=VDD vertical M2 bus
    need_west_hiz_vdd = any(pin_map.get(p, ("", "UNUSED"))[1] in ("IN", "UNUSED") for p in ("P3", "P4", "P5", "P6"))
    need_east_hiz_vdd = any(pin_map.get(p, ("", "UNUSED"))[1] in ("IN", "UNUSED") for p in ("P11", "P12", "P13", "P14"))

    # North VDD M1 Bus (y = 1826.0..1834.0, width = 8.0 um)
    nx_min = 6000 if need_west_hiz_vdd else 28000
    nx_max = 1834000 if need_east_hiz_vdd else 1818800
    add_box(core_cell, li_m1, nx_min, 1826000, nx_max, 1834000)
    for vx in (29700, 623700, 1223100, 1817100):
        add_via1(core_cell, li_m1, li_v1, li_m2, vx, 1828000)
        add_via1(core_cell, li_m1, li_v1, li_m2, vx, 1832000)

    # South VDD M1 Bus (y = 10.0..14.0, width = 4.0 um — cleanly above South pad M1 stub -3.4..6.0 and below core pins 16..25)
    add_box(core_cell, li_m1, 28000, 10000, 1818800, 14000)
    for vx in (29700, 623700, 1223100, 1817100):
        add_via1(core_cell, li_m1, li_v1, li_m2, vx, 12000)

    if not include_frame_bridges:
        return

    # 13 x 8.0um-wide M1 fingers connecting North VDD M1 bus to P16 VDDPAD M1 bar (x=970..1270, y=1840..1854)
    for xf in range(990000, 1240000, 20000):
        add_box(core_cell, li_m1, xf, 1826000, xf + 8000, 1844000)

    # West & East VSS bridges below y = 300 um (clear of West/East HIZ_VDD buses at y >= 338.3 um)
    for y_vss in (27000, 172800):
        add_box(core_cell, li_m2, x_west_vss, y_vss, 26000, y_vss + 3400)
        add_box(core_cell, li_m1, 1810000, y_vss, 1836700, y_vss + 3400)
        add_via1(core_cell, li_m1, li_v1, li_m2, 1835000, y_vss + 1700)
        add_box(core_cell, li_m2, 1833300, y_vss, x_east_vss, y_vss + 3400)

    # West HIZ_VDD vertical M2 bus (x = 6.0..9.4, y = 338.3..1834.0)
    if need_west_hiz_vdd:
        add_box(core_cell, li_m2, 6000, 338300, 9400, 1834000)
        add_via1(core_cell, li_m1, li_v1, li_m2, 7700, 1828000)
        add_via1(core_cell, li_m1, li_v1, li_m2, 7700, 1832000)

    # East HIZ_VDD vertical M2 bus (x = 1830.6..1834.0, y = 338.3..1834.0)
    if need_east_hiz_vdd:
        add_box(core_cell, li_m2, 1830600, 338300, 1834000, 1834000)
        add_via1(core_cell, li_m1, li_v1, li_m2, 1832300, 1828000)
        add_via1(core_cell, li_m1, li_v1, li_m2, 1832300, 1832000)

    # =========================================================================
    # Generic 14-Signal-Pad Routing (IN / OUT / UNUSED across N, S, W, E)
    # =========================================================================
    for pad, (edge, pad_c, out_c, hiz_c, in_pin, out_pin) in TR1UM_PAD_GEOM.items():
        _, direction = pin_map.get(pad, ("", "UNUSED"))
        pc = int(round(pad_c * 1000))
        oc = int(round(out_c * 1000))
        hc = int(round(hiz_c * 1000))

        if edge == "N":
            if direction == "IN":
                # PAD -> core M2 pin (straight down over M1 VDD bus)
                add_box(core_cell, li_m2, pc - 1700, 1795000, pc + 1700, 1843400)
                # HIZ -> North M1 VDD bus
                add_box(core_cell, li_m1, hc - 1700, 1826000, hc + 1700, 1843400)
                # OUT -> North M2 VSS ring
                add_box(core_cell, li_m2, oc - 6000, 1840000, oc + 6000, 1843400)
            elif direction == "OUT":
                # OUT -> core M2 pin
                add_box(core_cell, li_m2, oc - 1700, 1795000, oc + 1700, 1843400)
                # HIZ -> North M2 VSS ring
                add_box(core_cell, li_m2, hc - 6000, 1840000, hc + 6000, 1843400)
            else:  # UNUSED: HIZ=VDD, OUT=VSS
                add_box(core_cell, li_m1, hc - 1700, 1826000, hc + 1700, 1843400)
                add_box(core_cell, li_m2, oc - 6000, 1840000, oc + 6000, 1843400)

        elif edge == "S":
            if direction == "IN":
                # PAD -> M1 stub (-3.4..6.0) + V1(pc, 4.3) + M2 up to core pin (y=16..25), clearing South M1 VDD bus (10..14)
                add_box(core_cell, li_m1, pc - 1700, -3400, pc + 1700, 6000)
                add_via1(core_cell, li_m1, li_v1, li_m2, pc, 4300)
                add_box(core_cell, li_m2, pc - 1700, 2600, pc + 1700, 25000)
                # HIZ -> South M1 VDD bus (y=10..14)
                add_box(core_cell, li_m1, hc - 1700, -3400, hc + 1700, 14000)
                # OUT -> South M2 VSS ring
                add_box(core_cell, li_m2, oc - 6000, -3400, oc + 6000, 0)
            elif direction == "OUT":
                # OUT -> M1 stub (-3.4..6.0) + V1(oc, 4.3) + M2 up to core pin (y=16..25)
                add_box(core_cell, li_m1, oc - 1700, -3400, oc + 1700, 6000)
                add_via1(core_cell, li_m1, li_v1, li_m2, oc, 4300)
                add_box(core_cell, li_m2, oc - 1700, 2600, oc + 1700, 25000)
                # HIZ -> South M2 VSS ring
                add_box(core_cell, li_m2, hc - 6000, -3400, hc + 6000, 0)
            else:  # UNUSED
                add_box(core_cell, li_m1, hc - 1700, -3400, hc + 1700, 14000)
                add_box(core_cell, li_m2, oc - 6000, -3400, oc + 6000, 0)

        elif edge == "W":
            if direction == "IN":
                _, px1, py1, px2, py2 = in_pin
                py1_n, py2_n = int(round(py1 * 1000)), int(round(py2 * 1000))
                # PAD -> M1 jog at x=13..16.4 -> core pin M1
                add_box(core_cell, li_m1, -3400, pc - 1700, 16400, pc + 1700)
                add_box(core_cell, li_m1, 13000, min(pc - 1700, py1_n), 16400, max(pc + 1700, py2_n))
                add_box(core_cell, li_m1, 13000, py1_n, int(round(px2 * 1000)), py2_n)
                # HIZ -> West M2 HIZ_VDD bus (x=6..9.4)
                add_box(core_cell, li_m1, -3400, hc - 1700, 9400, hc + 1700)
                add_via1(core_cell, li_m1, li_v1, li_m2, 7700, hc)
                # OUT -> West M2 VSS ring
                add_box(core_cell, li_m2, -3400, oc - 6000, 0, oc + 6000)
            elif direction == "OUT":
                _, px1, py1, px2, py2 = out_pin
                py1_n, py2_n = int(round(py1 * 1000)), int(round(py2 * 1000))
                add_box(core_cell, li_m1, -3400, oc - 1700, 16400, oc + 1700)
                add_box(core_cell, li_m1, 13000, min(oc - 1700, py1_n), 16400, max(oc + 1700, py2_n))
                add_box(core_cell, li_m1, 13000, py1_n, int(round(px2 * 1000)), py2_n)
                # HIZ -> West M2 VSS ring
                add_box(core_cell, li_m2, -3400, hc - 6000, 0, hc + 6000)
            else:  # UNUSED
                add_box(core_cell, li_m1, -3400, hc - 1700, 9400, hc + 1700)
                add_via1(core_cell, li_m1, li_v1, li_m2, 7700, hc)
                add_box(core_cell, li_m2, -3400, oc - 6000, 0, oc + 6000)

        elif edge == "E":
            if direction == "IN":
                _, px1, py1, px2, py2 = in_pin
                py1_n, py2_n = int(round(py1 * 1000)), int(round(py2 * 1000))
                add_box(core_cell, li_m1, 1825000, pc - 1700, 1843400, pc + 1700)
                add_box(core_cell, li_m1, 1825000, min(pc - 1700, py1_n), 1828400, max(pc + 1700, py2_n))
                add_box(core_cell, li_m1, int(round(px1 * 1000)), py1_n, 1828400, py2_n)
                # HIZ -> East M2 HIZ_VDD bus (x=1830.6..1834.0)
                add_box(core_cell, li_m1, 1830600, hc - 1700, 1843400, hc + 1700)
                add_via1(core_cell, li_m1, li_v1, li_m2, 1832300, hc)
                # OUT -> East M2 VSS ring
                add_box(core_cell, li_m2, 1840000, oc - 6000, 1843400, oc + 6000)
            elif direction == "OUT":
                _, px1, py1, px2, py2 = out_pin
                py1_n, py2_n = int(round(py1 * 1000)), int(round(py2 * 1000))
                add_box(core_cell, li_m1, 1825000, oc - 1700, 1843400, oc + 1700)
                add_box(core_cell, li_m1, 1825000, min(oc - 1700, py1_n), 1828400, max(oc + 1700, py2_n))
                add_box(core_cell, li_m1, int(round(px1 * 1000)), py1_n, 1828400, py2_n)
                # HIZ -> East M2 VSS ring
                add_box(core_cell, li_m2, 1840000, hc - 6000, 1843400, hc + 6000)
            else:  # UNUSED
                add_box(core_cell, li_m1, 1830600, hc - 1700, 1843400, hc + 1700)
                add_via1(core_cell, li_m1, li_v1, li_m2, 1832300, hc)
                add_box(core_cell, li_m2, 1840000, oc - 6000, 1843400, oc + 6000)


def main() -> None:
    design, pdk = load_design_and_pdk(ROOT)
    top_module = design["design"]["top_module"]
    top_cell = design["design"]["top_cell"]
    pin_entries = parse_pin_order(ROOT / design["design"]["constraints"]["pin_order"])
    pin_map = {e["pad"]: (e["signal"], e["direction"]) for e in pin_entries}

    def_path = ROOT / "output/work" / f"{top_module}_routed.def"
    stdcell_gds = ROOT / pdk["views"]["stdcell_gds"]
    frame_gds = ROOT / pdk["views"]["frame_gds"]

    gds_dir = ROOT / "output/gds"
    gds_dir.mkdir(parents=True, exist_ok=True)
    out_core = gds_dir / f"{top_module}_core.gds"
    out_sub = gds_dir / f"{top_cell}.gds"

    components, pins, m1_rects, m2_rects, v1_pts = parse_def(def_path)
    print(f"DEF loaded: {len(components)} components, {len(pins)} pins, {len(m1_rects)} M1, {len(m2_rects)} M2, {len(v1_pts)} V1.")

    # 1. Core-only GDS
    lay_core = pya.Layout()
    lay_core.dbu = 0.001
    c_core_only = lay_core.create_cell(top_module)
    build_core(c_core_only, lay_core, stdcell_gds, components, pins, m1_rects, m2_rects, v1_pts, pin_map, include_frame_bridges=False)
    lay_core.write(str(out_core))
    print(f"Wrote {out_core.relative_to(ROOT)}")

    # 2. Full-chip MPW submission GDS (<top_cell> -> OSS_FRAME -> <top_module>)
    lay_chip = pya.Layout()
    lay_chip.dbu = 0.001

    l_frame = pya.Layout()
    l_frame.read(str(frame_gds))
    src_gio = l_frame.cell("OSS_FRAME_GIO")

    c_frame = lay_chip.create_cell("OSS_FRAME")
    c_frame.copy_tree(src_gio)

    li_txt = lay_chip.layer(49, 0)
    c_frame.shapes(li_txt).clear()
    pad_labels = []
    for pad, (px, py) in PAD_LABEL_COORDS.items():
        if pad == "P16":
            lbl = "VDD"
        elif pad == "P8":
            lbl = "VSS"
        else:
            lbl = pad
        pad_labels.append((lbl, px, py))
        c_frame.shapes(li_txt).insert(pya.Text(lbl, pya.Trans(px, py)))

    c_core = lay_chip.create_cell(top_module)
    build_core(c_core, lay_chip, stdcell_gds, components, pins, m1_rects, m2_rects, v1_pts, pin_map, include_frame_bridges=True)
    c_frame.insert(pya.CellInstArray(c_core.cell_index(), pya.Trans(0, False, CORE_OFFSET_X, CORE_OFFSET_Y)))

    c_sub = lay_chip.create_cell(top_cell)
    c_sub.insert(pya.CellInstArray(c_frame.cell_index(), pya.Trans(0, False, 0, 0)))
    for lbl, px, py in pad_labels:
        c_sub.shapes(li_txt).insert(pya.Text(lbl, pya.Trans(px, py)))

    lay_chip.write(str(out_sub))
    print(f"Wrote {out_sub.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
