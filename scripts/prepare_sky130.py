#!/usr/bin/env python3
"""
Prepare merged EDA views for Google / SkyWater SKY130 (sky130_fd_sc_hd)
into output/pdk_cache/sky130/ without dirtying the pdk/sky130 Git submodule.

Supports two layouts automatically:
  1) Raw google/skywater-pdk submodule at pdk/sky130/
     (libraries/sky130_fd_sc_hd/latest/{tech,timing,cells})
  2) Pre-built open_pdks / volare sky130A tree at pdk/sky130/ (or $SKY130A_ROOT)
     (libs.ref/sky130_fd_sc_hd/* and libs.tech/klayout/*)
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "output/pdk_cache/sky130"


def find_klayout() -> str | None:
    if shutil.which("klayout"):
        return shutil.which("klayout")
    mac_bin = Path("/Applications/klayout.app/Contents/MacOS/klayout")
    if mac_bin.is_file():
        return str(mac_bin)
    return None


def copy_if_exists(src: Path, dst: Path) -> bool:
    if src.is_file():
        shutil.copy2(src, dst)
        print(f"  [OK] {dst.relative_to(ROOT)} <- {src}")
        return True
    return False


def merge_lefs(cells_dir: Path, out_lef: Path) -> int:
    lef_files = sorted(cells_dir.glob("*/*.magic.lef")) or sorted(cells_dir.glob("*/*.lef"))
    if not lef_files:
        return 0
    macros: list[str] = []
    for lf in lef_files:
        text = lf.read_text(encoding="utf-8", errors="replace")
        # Extract MACRO ... END <name> blocks
        for m in re.finditer(r"^\s*MACRO\s+(\S+).*?^\s*END\s+\1\b", text, flags=re.MULTILINE | re.DOTALL):
            macros.append(m.group(0).strip())
    header = "VERSION 5.7 ;\nBUSBITCHARS \"[]\" ;\nDIVIDERCHAR \"/\" ;\n\n"
    footer = "\nEND LIBRARY\n"
    out_lef.write_text(header + "\n\n".join(macros) + footer, encoding="utf-8")
    print(f"  [OK] {out_lef.relative_to(ROOT)} ({len(macros)} MACROs merged)")
    return len(macros)


def merge_verilog(lib_root: Path, out_v: Path, out_prim_v: Path) -> int:
    cells_dir = lib_root / "cells"
    v_files = sorted(cells_dir.glob("*/*.functional.v"))
    if not v_files:
        v_files = [p for p in sorted(cells_dir.glob("*/*.v")) if not p.name.endswith(".tb.v")]
    parts: list[str] = []
    for vf in v_files:
        parts.append(f"// Source: {vf.name}\n" + vf.read_text(encoding="utf-8", errors="replace"))
    out_v.write_text("\n".join(parts) + "\n", encoding="utf-8")

    # Collect UDP primitives if present under models/
    models_dir = lib_root / "models"
    prim_files = sorted(models_dir.glob("**/*.v")) if models_dir.is_dir() else []
    prim_parts = [pf.read_text(encoding="utf-8", errors="replace") for pf in prim_files if not pf.name.endswith(".tb.v")]
    out_prim_v.write_text("\n".join(prim_parts) + "\n", encoding="utf-8")
    print(f"  [OK] {out_v.relative_to(ROOT)} ({len(v_files)} cell Verilog files merged)")
    print(f"  [OK] {out_prim_v.relative_to(ROOT)} ({len(prim_files)} primitive files merged)")
    return len(v_files)


def merge_spice(cells_dir: Path, out_sp: Path) -> int:
    sp_files = sorted(cells_dir.glob("*/*.spice"))
    if not sp_files:
        return 0
    parts = [f"* Source: {sf.name}\n" + sf.read_text(encoding="utf-8", errors="replace") for sf in sp_files]
    out_sp.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"  [OK] {out_sp.relative_to(ROOT)} ({len(sp_files)} SPICE files merged)")
    return len(sp_files)


def merge_gds_via_klayout(cells_dir: Path, out_gds: Path) -> bool:
    gds_files = sorted(cells_dir.glob("*/*.gds"))
    if not gds_files:
        return False
    klayout = find_klayout()
    if not klayout:
        print("  [WARN] KLayout not found; skipping merged sky130_fd_sc_hd.gds build.")
        return False
    helper = CACHE_DIR / "_merge_gds.py"
    env = os.environ.copy()
    env["SKY130_CELLS_DIR"] = str(cells_dir)
    env["SKY130_OUT_GDS"] = str(out_gds)
    helper.write_text(
        "import os, pya\n"
        "from pathlib import Path\n"
        "cells_dir = Path(os.environ['SKY130_CELLS_DIR'])\n"
        "out_gds = Path(os.environ['SKY130_OUT_GDS'])\n"
        "ly = pya.Layout()\n"
        "ly.dbu = 0.001\n"
        "files = sorted(cells_dir.glob('*/*.gds'))\n"
        "for f in files:\n"
        "    ly.read(str(f))\n"
        "ly.write(str(out_gds))\n"
        "print(f'Merged {len(files)} GDS files -> {out_gds}')\n",
        encoding="utf-8",
    )
    res = subprocess.run([klayout, "-b", "-r", str(helper)], env=env, capture_output=True, text=True)
    helper.unlink(missing_ok=True)
    if res.returncode != 0:
        print(f"  [WARN] KLayout GDS merge failed:\n{res.stderr}")
        return False
    print(f"  [OK] {out_gds.relative_to(ROOT)} ({len(gds_files)} GDS cells merged)")
    return True


def populate_from_sky130a(sky130a: Path) -> bool:
    ref = sky130a / "libs.ref/sky130_fd_sc_hd"
    tech = sky130a / "libs.tech/klayout"
    if not ref.is_dir():
        return False
    print(f"=== Populating SKY130 cache from compiled sky130A: {sky130a} ===")
    copy_if_exists(ref / "lib/sky130_fd_sc_hd__tt_025C_1v80.lib", CACHE_DIR / "sky130_fd_sc_hd__tt_025C_1v80.lib")
    if not copy_if_exists(ref / "techlef/sky130_fd_sc_hd__nom.tlef", CACHE_DIR / "sky130_fd_sc_hd.tlef"):
        copy_if_exists(ref / "techlef/sky130_fd_sc_hd.tlef", CACHE_DIR / "sky130_fd_sc_hd.tlef")
    copy_if_exists(ref / "lef/sky130_fd_sc_hd.lef", CACHE_DIR / "sky130_fd_sc_hd.lef")
    copy_if_exists(ref / "gds/sky130_fd_sc_hd.gds", CACHE_DIR / "sky130_fd_sc_hd.gds")
    copy_if_exists(ref / "spice/sky130_fd_sc_hd.spice", CACHE_DIR / "sky130_fd_sc_hd.spice")
    copy_if_exists(ref / "verilog/sky130_fd_sc_hd.v", CACHE_DIR / "sky130_fd_sc_hd.v")
    copy_if_exists(ref / "verilog/primitives.v", CACHE_DIR / "primitives.v")
    # KLayout DRC/LVS/lyp decks
    copy_if_exists(tech / "drc/sky130A_mr.drc", CACHE_DIR / "sky130A_mr.drc")
    copy_if_exists(tech / "lvs/sky130.lvs", CACHE_DIR / "sky130.lvs")
    copy_if_exists(tech / "tech/sky130A.lyp", CACHE_DIR / "sky130A.lyp")
    return True


def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pdk_dir = ROOT / "pdk/sky130"
    env_sky130a = Path(os.environ["SKY130A_ROOT"]) if os.environ.get("SKY130A_ROOT") else None

    if env_sky130a and populate_from_sky130a(env_sky130a):
        print("SKY130 preparation complete (from SKY130A_ROOT).")
        return

    if (pdk_dir / "libs.ref/sky130_fd_sc_hd").is_dir():
        populate_from_sky130a(pdk_dir)
        print("SKY130 preparation complete (from pdk/sky130 sky130A layout).")
        return

    raw_lib = pdk_dir / "libraries/sky130_fd_sc_hd/latest"
    if not raw_lib.is_dir():
        print(
            "ERROR: SKY130 standard cell library not found.\n"
            "  Expected either:\n"
            "    - pdk/sky130/libraries/sky130_fd_sc_hd/latest (google/skywater-pdk submodule)\n"
            "      Run: git -C pdk/sky130 submodule update --init libraries/sky130_fd_sc_hd/latest\n"
            "    - pdk/sky130/libs.ref/sky130_fd_sc_hd (or SKY130A_ROOT=... for open_pdks/volare sky130A)",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"=== Preparing SKY130 merged views from google/skywater-pdk: {raw_lib} ===")
    tlef = raw_lib / "tech/sky130_fd_sc_hd.tlef"
    copy_if_exists(tlef, CACHE_DIR / "sky130_fd_sc_hd.tlef")

    lib_file = raw_lib / "timing/sky130_fd_sc_hd__tt_025C_1v80.lib"
    if not copy_if_exists(lib_file, CACHE_DIR / "sky130_fd_sc_hd__tt_025C_1v80.lib"):
        print(
            "  [WARN] Timing .lib not found yet. Generate it with:\n"
            "         make -C pdk/sky130 timing",
            file=sys.stderr,
        )

    cells_dir = raw_lib / "cells"
    merge_lefs(cells_dir, CACHE_DIR / "sky130_fd_sc_hd.lef")
    merge_verilog(raw_lib, CACHE_DIR / "sky130_fd_sc_hd.v", CACHE_DIR / "primitives.v")
    merge_spice(cells_dir, CACHE_DIR / "sky130_fd_sc_hd.spice")
    merge_gds_via_klayout(cells_dir, CACHE_DIR / "sky130_fd_sc_hd.gds")

    print("SKY130 preparation complete (from google/skywater-pdk submodule).")


if __name__ == "__main__":
    main()
