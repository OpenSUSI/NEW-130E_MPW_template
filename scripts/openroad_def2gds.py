#!/usr/bin/env python3
"""
Generic OpenROAD Routed DEF -> Full-Chip/Macro GDSII Converter (KLayout Python).
Used by openroad_std flow_driver (IHP SG13G2, SKY130, NEW-130E).

Run with:
  klayout -b -r scripts/openroad_def2gds.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pya

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from config_loader import load_design_and_pdk


def main() -> None:
    design, pdk = load_design_and_pdk(ROOT)
    top_module = design["design"]["top_module"]
    top_cell = design["design"]["top_cell"]

    views = pdk.get("views", {})
    tech_lef = ROOT / views["tech_lef"]
    cells_lef = ROOT / views["drt_cells_lef"]
    stdcell_gds = ROOT / views["stdcell_gds"]
    klayout_map = views.get("klayout_map", "")
    routed_def = ROOT / f"output/work/{top_module}_routed.def"
    out_gds = ROOT / f"output/gds/{top_cell}.gds"

    if not routed_def.is_file():
        raise FileNotFoundError(f"Routed DEF not found: {routed_def}")
    if not stdcell_gds.is_file():
        raise FileNotFoundError(f"Standard cell GDS not found: {stdcell_gds}")

    opt = pya.LoadLayoutOptions()
    lefdef = opt.lefdef_config
    lefdef.lef_files = [str(tech_lef), str(cells_lef)]
    lefdef.read_lef_with_def = True
    lefdef.produce_cell_outlines = False
    lefdef.produce_placement_blockages = False
    lefdef.produce_obstructions = False
    lefdef.produce_via_geometry = True
    lefdef.produce_routing = True
    lefdef.produce_pins = True
    lefdef.produce_labels = True
    lefdef.produce_special_routing = True
    if klayout_map and (ROOT / klayout_map).is_file():
        lefdef.map_file = str(ROOT / klayout_map)

    layout = pya.Layout()
    layout.read(str(routed_def), opt)

    # Read standard cell physical GDS and replace abstract LEF cells with physical layouts
    lib_layout = pya.Layout()
    lib_layout.read(str(stdcell_gds))

    lib_cells = {c.name: c for c in lib_layout.each_cell()}
    replaced = 0
    for cell in list(layout.each_cell()):
        if cell.name in lib_cells:
            cell.clear()
            cell.copy_tree(lib_cells[cell.name])
            replaced += 1

    # Rename top cell to MPW submission top_cell
    top_cells = list(layout.top_cells())
    if len(top_cells) == 1 and top_cells[0].name != top_cell:
        top_cells[0].name = top_cell

    out_gds.parent.mkdir(parents=True, exist_ok=True)
    layout.write(str(out_gds))
    print(f"Wrote GDSII: {out_gds.relative_to(ROOT)} (top={top_cell}, replaced_stdcells={replaced})")


if __name__ == "__main__":
    main()
