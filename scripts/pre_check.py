#!/usr/bin/env python3
"""
KLayout-native MPW GDSII Precheck.
Run with:
  klayout -b -r scripts/pre_check.py -rd input=output/gds/<top>.gds -rd top_cell=<top>
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pya

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from config_loader import load_design_and_pdk

EPS = 1e-3


def fail(msg: str) -> None:
    print(f"PRECHECK FAIL: {msg}")
    sys.exit(1)


def same_float(a: float, b: float, eps: float = EPS) -> bool:
    return abs(a - b) <= eps


def main() -> None:
    design, pdk = load_design_and_pdk(ROOT)

    expected_top = globals().get("top_cell") or os.environ.get("DESIGN_TOP_CELL") or design["design"]["top_cell"]
    gds_path = globals().get("input") or os.environ.get("PRECHECK_GDS") or str(ROOT / "output/gds" / f"{expected_top}.gds")

    if not Path(gds_path).is_file():
        fail(f"GDS file not found: {gds_path}")

    geom = pdk["geometry"]
    tech = pdk["technology"]
    die_w = float(geom["die_width_um"])
    die_h = float(geom["die_height_um"])
    expected_dbu = float(tech["dbu_um"])
    frame_cells = set(geom.get("frame_cells", []))

    layout = pya.Layout()
    layout.read(str(gds_path))

    top_cells = list(layout.top_cells())
    if len(top_cells) == 0:
        fail(f"No top-level cell found in '{gds_path}'.")
    if len(top_cells) > 1:
        names = ", ".join(c.name for c in top_cells)
        fail(f"Multiple top-level cells found in '{gds_path}': {names}")

    tc = top_cells[0]
    if tc.name != expected_top:
        fail(f"Top cell name '{tc.name}' != expected '{expected_top}'.")
    print(f"OK: Top cell name '{tc.name}' matches.")

    if not same_float(layout.dbu, expected_dbu, eps=1e-6):
        fail(f"DBU is {layout.dbu:.6g} um, expected {expected_dbu:.6g} um.")
    print(f"OK: DBU is {layout.dbu:.3f} um.")

    bbox = tc.dbbox()
    die_origin = geom.get("die_origin", "center")
    if die_origin == "zero":
        # Standard OpenROAD block/die coordinate space: (0, 0) to (die_w, die_h)
        if bbox.left < -EPS or bbox.bottom < -EPS or bbox.right > die_w + EPS or bbox.top > die_h + EPS:
            fail(
                f"Layout bbox ({bbox.left:.2f},{bbox.bottom:.2f})-({bbox.right:.2f},{bbox.top:.2f}) "
                f"exceeds die area (0.00,0.00)-({die_w:.2f},{die_h:.2f})."
            )
        print(f"OK: Layout bbox ({bbox.left:.1f},{bbox.bottom:.1f})-({bbox.right:.1f},{bbox.top:.1f}) fits within (0,0)-({die_w:.1f},{die_h:.1f}) um.")
    else:
        exp_p1 = (-die_w / 2.0, -die_h / 2.0)
        exp_p2 = (die_w / 2.0, die_h / 2.0)
        if not (
            same_float(bbox.left, exp_p1[0])
            and same_float(bbox.bottom, exp_p1[1])
            and same_float(bbox.right, exp_p2[0])
            and same_float(bbox.top, exp_p2[1])
        ):
            fail(
                f"Die bbox ({bbox.left:.2f},{bbox.bottom:.2f})-({bbox.right:.2f},{bbox.top:.2f}) "
                f"!= expected ({exp_p1[0]:.2f},{exp_p1[1]:.2f})-({exp_p2[0]:.2f},{exp_p2[1]:.2f})."
            )
        print(f"OK: Die bbox matches ({exp_p1[0]:.1f},{exp_p1[1]:.1f})-({exp_p2[0]:.1f},{exp_p2[1]:.1f}) um.")

    if frame_cells:
        present = {c.name for c in layout.each_cell()}
        if not (present & frame_cells):
            fail(f"None of required frame cells {sorted(frame_cells)} found in layout.")
        print(f"OK: Required OpenSUSI frame cell present ({sorted(present & frame_cells)}).")

    print("PRECHECK PASS")


if __name__ == "__main__":
    main()
