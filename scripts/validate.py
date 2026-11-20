#!/usr/bin/env python3
"""
Template Policy, Schema, Port-Mapping, and Sign-Off Gate Validator.
Enforces the OpenSUSI x Google AI-Assisted Chip Design Platform contract.

Usage:
  python3 scripts/validate.py --stage pre
  python3 scripts/validate.py --stage post
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from config_loader import load_design_and_pdk, parse_pin_order, repo_root


REQUIRED_PREFIX_DIRS = [
    "pdk",
    "rtl",
    "constraints",
    "verification/testbench",
    "flow",
    "scripts",
    ".github/workflows",
    "docs",
    "output/gds",
    "output/reports",
    "output/logs",
]

REQUIRED_PREFIX_FILES = [
    "README.md",
    "AGENTS.md",
    "GEMINI.md",
    "design.yaml",
    ".github/workflows/design-ci.yml",
    "docs/design-spec.md",
    "docs/ai-design-guide.md",
    "flow/synth.sh",
    "flow/floorplan.sh",
    "flow/place_route.sh",
    "flow/signoff.sh",
    "flow/run_all.sh",
    "scripts/validate.py",
    "scripts/package.py",
]


def parse_verilog_top_ports(rtl_paths: list[Path], top_module: str) -> dict[str, str]:
    """Return dict[scalar_signal_name -> direction ('IN'|'OUT'|'INOUT')] for top_module."""
    combined = "\n".join(p.read_text(encoding="utf-8") for p in rtl_paths)
    # Strip C-style and line comments
    combined = re.sub(r"/\*.*?\*/", "", combined, flags=re.DOTALL)
    combined = re.sub(r"//.*", "", combined)

    m = re.search(rf"\bmodule\s+{re.escape(top_module)}\b\s*(?:#\s*\([^)]*\))?\s*\((.*?)\)\s*;", combined, re.DOTALL)
    if not m:
        raise ValueError(f"Top module '{top_module}' not found in RTL files")
    header_ports = m.group(1)

    ports: dict[str, str] = {}
    dir_map = {"input": "IN", "output": "OUT", "inout": "INOUT"}

    # ANSI-style port declarations inside module(...)
    port_decl_re = re.compile(
        r"\b(input|output|inout)\b\s*(?:wire|reg|logic)?\s*(?:signed)?\s*(?:\[\s*(\d+)\s*:\s*(\d+)\s*\])?\s*([A-Za-z_][A-Za-z0-9_]*)"
    )
    for dm in port_decl_re.finditer(header_ports):
        pdir = dir_map[dm.group(1)]
        msb, lsb, name = dm.group(2), dm.group(3), dm.group(4)
        if msb is not None and lsb is not None:
            hi, lo = int(msb), int(lsb)
            step = 1 if hi >= lo else -1
            for bit in range(lo, hi + step, step):
                ports[f"{name}[{bit}]"] = pdir
        else:
            ports[name] = pdir

    if not ports:
        raise ValueError(f"Could not extract ANSI ports for module '{top_module}'. Use Verilog-2001 ANSI port style.")
    return ports


def validate_pre(root: Path) -> list[str]:
    errors: list[str] = []

    # 1. Prefix folder and file policy
    for d in REQUIRED_PREFIX_DIRS:
        if not (root / d).is_dir():
            errors.append(f"[PREFIX] Missing required directory: {d}")
    for f in REQUIRED_PREFIX_FILES:
        if not (root / f).is_file():
            errors.append(f"[PREFIX] Missing required file: {f}")

    if errors:
        return errors

    # 2. Load design.yaml and active pdk.yaml
    try:
        design, pdk = load_design_and_pdk(root)
    except Exception as exc:
        return [f"[SCHEMA] Failed loading design.yaml / pdk.yaml: {exc}"]

    # 3. Validate design.yaml schema
    if design.get("schema_version") != 1:
        errors.append(f"[SCHEMA] Unsupported schema_version: {design.get('schema_version')} (expected 1)")

    for sec in ("project", "pdk", "design", "targets", "verification", "signoff"):
        if not isinstance(design.get(sec), dict):
            errors.append(f"[SCHEMA] Missing section '{sec}' in design.yaml")

    des = design.get("design", {})
    top_module = des.get("top_module", "")
    top_cell = des.get("top_cell", "")
    prefix = pdk.get("technology", {}).get("top_cell_prefix", "")
    if not top_module:
        errors.append("[SCHEMA] design.top_module is empty")
    if not top_cell:
        errors.append("[SCHEMA] design.top_cell is empty")
    elif prefix and not top_cell.startswith(prefix):
        errors.append(f"[POLICY] design.top_cell '{top_cell}' must start with PDK prefix '{prefix}'")
    if top_cell and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", top_cell):
        errors.append(f"[POLICY] design.top_cell '{top_cell}' contains invalid characters")

    # 4. Validate single-target PDK policy & PDK readiness
    pdk_root = root / "pdk"
    mounted_pdks = sorted(
        d.name for d in pdk_root.iterdir()
        if d.is_dir() and d.name != "profiles" and not d.name.startswith(".")
    )
    if len(mounted_pdks) > 1:
        errors.append(
            f"[POLICY] Multiple target PDK directories mounted under pdk/: {', '.join(mounted_pdks)}. "
            "Each design repository must select exactly ONE target PDK."
        )

    if pdk.get("status") == "scaffold":
        errors.append(
            f"[PDK] Active PDK '{pdk.get('name')}' is still in 'scaffold' state. "
            "Mount the target PDK submodule under pdk/<name>/ and update pdk/profiles/<name>.yaml, "
            "or switch pdk.name to 'tr1um' for PoC."
        )
    else:
        active_pdk_dir = pdk_root / str(pdk.get("name", ""))
        if not active_pdk_dir.is_dir() or not any(active_pdk_dir.iterdir()):
            errors.append(
                f"[PDK] Target PDK directory 'pdk/{pdk.get('name')}' is missing or empty "
                "(if using a Git submodule, run: git submodule update --init --recursive)."
            )
        required_views = ["liberty", "tech_lef", "grt_cells_lef", "drt_cells_lef", "stdcell_gds", "primitives_v"]
        if pdk.get("padframe", {}).get("total_pads", 0) > 0 or pdk.get("views", {}).get("frame_gds"):
            required_views.append("frame_gds")
        for view_key in required_views:
            rel = pdk.get("views", {}).get(view_key)
            if not rel or not (root / rel).exists():
                hint = " (for sky130, run: python3 scripts/prepare_sky130.py)" if rel and "pdk_cache/sky130" in str(rel) else ""
                errors.append(f"[PDK] Missing view '{view_key}': {rel}{hint}")
        d_sig = design.get("signoff", {})
        if d_sig.get("drc", True):
            rel = pdk.get("signoff", {}).get("drc_deck")
            if not rel or not (root / rel).exists():
                errors.append(f"[PDK] Missing sign-off deck 'drc_deck': {rel}")
        if d_sig.get("lvs", {}).get("enabled", True):
            rel = pdk.get("signoff", {}).get("lvs_deck")
            if not rel or not (root / rel).exists():
                errors.append(f"[PDK] Missing sign-off deck 'lvs_deck': {rel}")

    # 5. Validate RTL, constraints, testbench existence
    rtl_rel = des.get("rtl_files", [])
    if not rtl_rel:
        errors.append("[DESIGN] design.rtl_files is empty")
    rtl_paths = [root / p for p in rtl_rel]
    for p in rtl_paths:
        if not p.is_file():
            errors.append(f"[DESIGN] Missing RTL file: {p.relative_to(root)}")

    sdc_path = root / des.get("constraints", {}).get("sdc", "")
    pin_path = root / des.get("constraints", {}).get("pin_order", "")
    tb_path = root / design.get("verification", {}).get("testbench", "")
    for label, p in [("SDC", sdc_path), ("pin_order.cfg", pin_path), ("testbench", tb_path)]:
        if not p.is_file():
            errors.append(f"[DESIGN] Missing {label}: {p}")

    if errors:
        return errors

    # 6. Cross-check RTL ports vs constraints/pin_order.cfg vs PDK padframe
    try:
        rtl_ports = parse_verilog_top_ports(rtl_paths, top_module)
        pin_entries = parse_pin_order(pin_path)
    except Exception as exc:
        errors.append(f"[PINS] {exc}")
        return errors

    seen_pads: set[str] = set()
    mapped_signals: dict[str, str] = {}
    valid_sig_pads = set(pdk.get("padframe", {}).get("signal_pads", []))
    pwr_pads = pdk.get("padframe", {}).get("power_pads", {})
    valid_all_pads = valid_sig_pads | set(pwr_pads.values())

    for entry in pin_entries:
        pad = entry["pad"]
        sig = entry["signal"]
        direction = entry["direction"]
        if pad in seen_pads:
            errors.append(f"[PINS] Duplicate pad assignment: {pad}")
        seen_pads.add(pad)
        if valid_all_pads and pad not in valid_all_pads:
            errors.append(f"[PINS] Unknown pad '{pad}' for PDK '{pdk.get('name')}'")
        if direction not in ("IN", "OUT", "POWER", "UNUSED"):
            errors.append(f"[PINS] Invalid direction '{direction}' on pad {pad}")
        if direction == "POWER":
            if pad == pwr_pads.get("vdd") and sig != "VDD":
                errors.append(f"[PINS] Power pad {pad} must be mapped to VDD, got '{sig}'")
            if pad == pwr_pads.get("vss") and sig != "VSS":
                errors.append(f"[PINS] Power pad {pad} must be mapped to VSS, got '{sig}'")
        elif direction in ("IN", "OUT"):
            if valid_sig_pads and pad not in valid_sig_pads:
                errors.append(f"[PINS] Signal '{sig}' assigned to non-signal pad '{pad}'")
            if sig in mapped_signals:
                errors.append(f"[PINS] Signal '{sig}' mapped to multiple pads")
            mapped_signals[sig] = direction

    for port_name, port_dir in sorted(rtl_ports.items()):
        if port_name not in mapped_signals:
            errors.append(f"[PINS] RTL port '{port_name}' ({port_dir}) is not mapped in pin_order.cfg")
        elif mapped_signals[port_name] != port_dir:
            errors.append(
                f"[PINS] Direction mismatch for '{port_name}': RTL has {port_dir}, pin_order.cfg has {mapped_signals[port_name]}"
            )
    for sig_name in sorted(mapped_signals):
        if sig_name not in rtl_ports:
            errors.append(f"[PINS] pin_order.cfg signal '{sig_name}' does not exist on RTL module '{top_module}'")

    clk_port = design.get("targets", {}).get("clock_port", "clk")
    if clk_port and clk_port not in rtl_ports:
        errors.append(f"[TARGETS] clock_port '{clk_port}' not found in RTL module '{top_module}'")

    return errors


def validate_post(root: Path) -> list[str]:
    errors = validate_pre(root)
    summary_path = root / "output/reports/summary.json"
    if not summary_path.is_file():
        errors.append("[SIGNOFF] Missing output/reports/summary.json (run flow/run_all.sh first)")
        return errors

    summary: dict[str, Any] = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("overall_status") != "PASS":
        errors.append(f"[SIGNOFF] overall_status is '{summary.get('overall_status')}' (expected 'PASS')")

    checks = summary.get("checks", {})
    for key in ("rtl_sim", "synth", "gl_sim", "floorplan", "route", "precheck", "drc", "lvs", "mdp_ip62"):
        if checks.get(key) != "PASS":
            errors.append(f"[SIGNOFF] Gate '{key}' did not pass: {checks.get(key)}")

    design, _ = load_design_and_pdk(root)
    top_cell = design["design"]["top_cell"]
    for rel in (f"output/gds/{top_cell}.gds", f"output/gds/{top_cell}.cir"):
        if not (root / rel).is_file():
            errors.append(f"[ARTIFACTS] Missing required output artifact: {rel}")

    targets = design.get("targets", {})
    metrics = summary.get("metrics", {})
    max_cells = targets.get("max_stdcells")
    if max_cells is not None and metrics.get("stdcell_count", 0) > max_cells:
        errors.append(f"[PPA] stdcell_count {metrics.get('stdcell_count')} exceeds target max_stdcells {max_cells}")
    max_util = targets.get("max_utilization_pct")
    if max_util is not None and metrics.get("utilization_pct", 0.0) > max_util:
        errors.append(f"[PPA] utilization_pct {metrics.get('utilization_pct')} exceeds target {max_util}%")
    wns = metrics.get("sta_wns_ns")
    if wns is not None and wns < 0.0:
        errors.append(f"[PPA] Negative STA WNS detected: {wns} ns")

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenSUSI Template & Sign-Off Validator")
    parser.add_argument("--stage", choices=["pre", "post"], default="pre")
    args = parser.parse_args()

    root = repo_root()
    errors = validate_pre(root) if args.stage == "pre" else validate_post(root)
    if errors:
        print(f"VALIDATION FAILED (stage={args.stage}): {len(errors)} issue(s)")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)

    print(f"VALIDATION PASSED (stage={args.stage})")


if __name__ == "__main__":
    main()
