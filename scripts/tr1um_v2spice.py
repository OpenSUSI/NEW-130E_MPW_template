#!/usr/bin/env python3
"""
Generic TR-1um LVS Reference SPICE Netlist (.cir) Generator.
Builds hierarchical SPICE: <top_cell> -> OSS_FRAME -> (OSS_ESD_5V_* pads + <top_module>)
directly from synthesized Verilog, placed DEF (FILL3/FILL2 decaps), and pin_order.cfg.
"""

from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from config_loader import load_design_and_pdk, parse_pin_order
from tr1um_place import parse_gate_verilog


def parse_spice_subckts(spice_text: str) -> dict[str, tuple[list[str], str]]:
    subckts: dict[str, tuple[list[str], str]] = {}
    lines = spice_text.splitlines()
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if re.match(r"^\.subckt\b", s, re.IGNORECASE):
            block = [lines[i]]
            header = s
            i += 1
            while i < len(lines) and lines[i].lstrip().startswith("+"):
                header += " " + lines[i].lstrip()[1:].strip()
                block.append(lines[i])
                i += 1
            toks = header.split()
            name = toks[1]
            pins = toks[2:]
            while i < len(lines):
                block.append(lines[i])
                if re.match(r"^\.ends\b", lines[i].strip(), re.IGNORECASE):
                    i += 1
                    break
                i += 1
            subckts[name] = (pins, "\n".join(block))
        else:
            i += 1
    return subckts


def load_subckts(stdcell_spice_dir: Path, pad_spice: Path) -> dict[str, tuple[list[str], str]]:
    subckts: dict[str, tuple[list[str], str]] = {}
    for sp in sorted(glob.glob(str(stdcell_spice_dir / "*.spice"))):
        subckts.update(parse_spice_subckts(Path(sp).read_text(encoding="utf-8")))
    subckts.update(parse_spice_subckts(pad_spice.read_text(encoding="utf-8")))
    return subckts


def parse_def_fillers(def_path: Path) -> list[tuple[str, str]]:
    fillers: list[tuple[str, str]] = []
    in_comp = False
    for line in def_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("COMPONENTS "):
            in_comp = True
            continue
        if in_comp and s.startswith("END COMPONENTS"):
            break
        if in_comp and s.startswith("- "):
            parts = s.split()
            if len(parts) >= 3 and parts[2].startswith("FILL"):
                fillers.append((parts[1], parts[2]))
    return fillers


def sanitize_spice_net(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\[\]]", "_", name)


def main() -> None:
    design, pdk = load_design_and_pdk(ROOT)
    top_module = design["design"]["top_module"]
    top_cell = design["design"]["top_cell"]

    syn_v = ROOT / "output/work" / f"{top_module}_syn.v"
    placed_def = ROOT / "output/work" / f"{top_module}_placed.def"
    stdcell_spice_dir = ROOT / pdk["views"]["stdcell_spice_dir"]
    pad_spice = ROOT / pdk["views"]["pad_spice"]
    pin_entries = parse_pin_order(ROOT / design["design"]["constraints"]["pin_order"])
    pin_map = {e["pad"]: (e["signal"], e["direction"]) for e in pin_entries}

    subckts = load_subckts(stdcell_spice_dir, pad_spice)
    instances, _ = parse_gate_verilog(syn_v)
    fillers = parse_def_fillers(placed_def)

    # Core ports in deterministic order
    sig_entries = [e for e in pin_entries if e["direction"] in ("IN", "OUT")]
    core_pins = [e["signal"] for e in sig_entries] + ["VDD", "VSS"]

    # 1. Build .SUBCKT <top_module>
    core_lines = [
        f"* Gate-level LVS core netlist for {top_module}",
        f".SUBCKT {top_module} " + " ".join(core_pins),
    ]
    used_cells: set[str] = set()
    floating_idx = 0

    for cell_type, inst_name, port_map in instances:
        if cell_type not in subckts:
            raise KeyError(f"Cell '{cell_type}' not found in SPICE libraries")
        used_cells.add(cell_type)
        pin_order, _ = subckts[cell_type]
        conns = []
        for p in pin_order:
            pl = p.lower()
            if pl in ("vdd", "vdd|pad", "pad|vdd"):
                conns.append("VDD")
            elif pl in ("vss", "gnd", "gnd|gnd", "pad|vss"):
                conns.append("VSS")
            elif p in port_map:
                conns.append(sanitize_spice_net(port_map[p]))
            else:
                # Unconnected optional output pin (e.g., QB on DFFRB/MUXDFFRB)
                conns.append(f"__nc_{floating_idx}")
                floating_idx += 1
        clean_inst = re.sub(r"[^A-Za-z0-9_]", "_", inst_name)
        core_lines.append(f"X{clean_inst} {' '.join(conns)} {cell_type}")

    for inst_name, cell_type in fillers:
        if cell_type not in subckts:
            continue
        used_cells.add(cell_type)
        pin_order, _ = subckts[cell_type]
        conns = ["VDD" if p.lower() == "vdd" else "VSS" for p in pin_order]
        clean_inst = re.sub(r"[^A-Za-z0-9_]", "_", inst_name)
        core_lines.append(f"X{clean_inst} {' '.join(conns)} {cell_type}")

    core_lines.append(f".ENDS {top_module}")

    # 2. Build .SUBCKT OSS_FRAME
    # OSS_ESD_5V_DIO pin order: PAD VDD HIZ OUT VSS
    # OSS_ESD_5V_VDD pin order: PAD|VDD VSS
    # OSS_ESD_5V_VSS pin order: VDD PAD|VSS
    all_sig_pads = ["P1", "P10", "P11", "P12", "P13", "P14", "P15", "P2", "P3", "P4", "P5", "P6", "P7", "P9"]
    top_pins = all_sig_pads + ["VDD", "VSS"]

    frame_lines = [
        "* Full-chip padframe + core netlist",
        ".SUBCKT OSS_FRAME " + " ".join(top_pins),
    ]
    core_net_map: dict[str, str] = {"VDD": "VDD", "VSS": "VSS"}

    for pad in all_sig_pads:
        sig, direction = pin_map.get(pad, ("", "UNUSED"))
        if direction == "IN":
            # PAD connected directly to core input; HIZ=VDD, OUT=VSS
            frame_lines.append(f"X{pad} {pad} VDD VDD VSS VSS OSS_ESD_5V_DIO")
            core_net_map[sig] = pad
        elif direction == "OUT":
            # Core output drives pad OUT pin; HIZ=VSS
            net_out = f"net_out_{pad}"
            frame_lines.append(f"X{pad} {pad} VDD VSS {net_out} VSS OSS_ESD_5V_DIO")
            core_net_map[sig] = net_out
        else:
            # UNUSED pad: HIZ=VDD, OUT=VSS
            frame_lines.append(f"X{pad} {pad} VDD VDD VSS VSS OSS_ESD_5V_DIO")

    frame_lines.append("XP16_VDD VDD VSS OSS_ESD_5V_VDD")
    frame_lines.append("XP8_VSS VDD VSS OSS_ESD_5V_VSS")

    core_conn = [core_net_map[p] for p in core_pins]
    frame_lines.append(f"Xcore {' '.join(core_conn)} {top_module}")
    frame_lines.append(".ENDS OSS_FRAME")

    # 3. Build top wrapper .SUBCKT <top_cell>
    wrapper_lines = [
        f"* Top-level MPW submission wrapper ({top_cell})",
        f".SUBCKT {top_cell} " + " ".join(top_pins),
        f"Xframe {' '.join(top_pins)} OSS_FRAME",
        f".ENDS {top_cell}",
    ]

    # Collect library subcircuits (all pad subckts + used stdcells)
    lib_blocks = []
    for name in sorted(subckts.keys()):
        if name in used_cells or name.startswith("OSS_"):
            lib_blocks.append(subckts[name][1])

    out_cir = ROOT / "output/gds" / f"{top_cell}.cir"
    out_cir.parent.mkdir(parents=True, exist_ok=True)
    content = "\n\n".join([
        f"* LVS Reference Netlist for {top_cell} (generated by scripts/tr1um_v2spice.py)",
        "\n".join(wrapper_lines),
        "\n".join(frame_lines),
        "\n".join(core_lines),
        "\n\n".join(lib_blocks),
        "",
    ])
    out_cir.write_text(content, encoding="utf-8")
    print(f"Wrote {out_cir.relative_to(ROOT)} ({len(instances)} logic cells, {len(fillers)} fillers, {len(lib_blocks)} subckts)")


if __name__ == "__main__":
    main()
