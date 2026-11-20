#!/usr/bin/env python3
"""
Shared configuration loader for OpenSUSI x Google AI-Assisted Chip Design Platform.
Zero external dependencies required (uses PyYAML if installed, else built-in parser).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Any


def _strip_comment(line: str) -> str:
    in_sq = False
    in_dq = False
    for idx, ch in enumerate(line):
        if ch == "'" and not in_dq:
            in_sq = not in_sq
        elif ch == '"' and not in_sq:
            in_dq = not in_dq
        elif ch == "#" and not in_sq and not in_dq:
            if idx == 0 or line[idx - 1].isspace():
                return line[:idx]
    return line


def _parse_scalar(val: str) -> Any:
    s = val.strip()
    if s == "" or s in ("null", "Null", "NULL", "~"):
        return None
    if s == "[]":
        return []
    if s == "{}":
        return {}
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if re.fullmatch(r"[+-]?\d+", s):
        return int(s)
    if re.fullmatch(r"[+-]?(\d+\.\d*|\.\d+)([eE][+-]?\d+)?", s):
        return float(s)
    return s


def _fallback_yaml_load(text: str) -> Any:
    raw_lines = []
    for line in text.splitlines():
        cleaned = _strip_comment(line).rstrip()
        if not cleaned.strip():
            continue
        indent = len(cleaned) - len(cleaned.lstrip(" "))
        raw_lines.append((indent, cleaned.strip()))

    def parse_block(idx: int, min_indent: int) -> tuple[Any, int]:
        if idx >= len(raw_lines):
            return {}, idx
        first_indent, first_content = raw_lines[idx]
        if first_content.startswith("- "):
            arr: list[Any] = []
            while idx < len(raw_lines):
                ind, content = raw_lines[idx]
                if ind < min_indent or ind != first_indent or not content.startswith("- "):
                    break
                item_str = content[2:].strip()
                idx += 1
                if item_str == "":
                    val, idx = parse_block(idx, ind + 1)
                    arr.append(val)
                elif ":" in item_str and not (item_str.startswith('"') or item_str.startswith("'")):
                    # Inline dict item in list (not used in our schemas, basic support)
                    k, _, v = item_str.partition(":")
                    d: dict[str, Any] = {k.strip(): _parse_scalar(v)}
                    if idx < len(raw_lines) and raw_lines[idx][0] > ind:
                        extra, idx = parse_block(idx, ind + 1)
                        if isinstance(extra, dict):
                            d.update(extra)
                    arr.append(d)
                else:
                    arr.append(_parse_scalar(item_str))
            return arr, idx

        obj: dict[str, Any] = {}
        while idx < len(raw_lines):
            ind, content = raw_lines[idx]
            if ind < min_indent:
                break
            if ind != first_indent:
                break
            if content.startswith("- "):
                break
            key, sep, rest = content.partition(":")
            if not sep:
                raise ValueError(f"Invalid YAML line: {content}")
            key = key.strip().strip('"').strip("'")
            rest = rest.strip()
            idx += 1
            if rest == "":
                if idx < len(raw_lines) and raw_lines[idx][0] > ind:
                    val, idx = parse_block(idx, raw_lines[idx][0])
                    obj[key] = val
                else:
                    obj[key] = None
            else:
                obj[key] = _parse_scalar(rest)
        return obj, idx

    result, _ = parse_block(0, 0)
    return result


def load_yaml(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text)
    except ImportError:
        data = _fallback_yaml_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {p}")
    return data


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_design_and_pdk(root: Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    base = root or repo_root()
    design = load_yaml(base / "design.yaml")
    pdk_profile = design.get("pdk", {}).get("profile")
    if not pdk_profile:
        pdk_name = design.get("pdk", {}).get("name", "tr1um")
        pdk_profile = f"pdk/{pdk_name}/pdk.yaml"
    pdk = load_yaml(base / pdk_profile)
    return design, pdk


def parse_pin_order(path: str | Path) -> list[dict[str, str]]:
    """Parse constraints/pin_order.cfg -> list of {pad, edge, signal, direction}."""
    entries: list[dict[str, str]] = []
    for lineno, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 4:
            raise ValueError(f"{path}:{lineno}: expected 4 columns (<PAD> <EDGE> <SIGNAL> <DIRECTION>), got: {raw}")
        pad, edge, signal, direction = parts
        entries.append({
            "pad": pad.upper(),
            "edge": edge.upper(),
            "signal": signal,
            "direction": direction.upper(),
        })
    return entries


def export_shell_vars(root: Path) -> str:
    design, pdk = load_design_and_pdk(root)
    d_des = design["design"]
    d_tgt = design.get("targets", {})
    d_sig = design.get("signoff", {})
    p_views = pdk.get("views", {})
    p_sig = pdk.get("signoff", {})
    p_syn = pdk.get("synthesis", {})
    p_tech = pdk.get("technology", {})

    kv = {
        "DESIGN_PROJECT_NAME": str(design["project"]["name"]),
        "DESIGN_TOP_MODULE": str(d_des["top_module"]),
        "DESIGN_TOP_CELL": str(d_des["top_cell"]),
        "DESIGN_RTL_FILES": " ".join(str(x) for x in d_des.get("rtl_files", [])),
        "DESIGN_SDC": str(d_des["constraints"]["sdc"]),
        "DESIGN_PIN_ORDER": str(d_des["constraints"]["pin_order"]),
        "DESIGN_TESTBENCH": str(design["verification"]["testbench"]),
        "DESIGN_CLOCK_PORT": str(d_tgt.get("clock_port", "clk")),
        "DESIGN_CLOCK_PERIOD_NS": str(d_tgt.get("clock_period_ns", 100.0)),
        "SIGNOFF_PRECHECK": "true" if d_sig.get("precheck", True) else "false",
        "SIGNOFF_DRC": "true" if d_sig.get("drc", True) else "false",
        "SIGNOFF_LVS_ENABLED": "true" if d_sig.get("lvs", {}).get("enabled", True) else "false",
        "SIGNOFF_LVS_NETLIST_ONLY": "true" if d_sig.get("lvs", {}).get("netlist_only", False) else "false",
        "SIGNOFF_MDP_ENABLED": "true" if d_sig.get("mdp", {}).get("enabled", True) else "false",
        "SIGNOFF_MDP_FILE": str(d_sig.get("mdp", {}).get("file", f"MDP_{d_des['top_cell']}.gds")),
        "SIGNOFF_STA_ENABLED": "true" if d_sig.get("sta", {}).get("enabled", True) else "false",
        "PDK_NAME": str(pdk["name"]),
        "PDK_FLOW_DRIVER": str(pdk.get("flow_driver", "tr1um_2m")),
        "PDK_METAL_LAYERS": str(p_tech.get("metal_layers", "METAL1-METAL2")),
        "PDK_LIBERTY": str(p_views.get("liberty", "")),
        "PDK_TECH_LEF": str(p_views.get("tech_lef", "")),
        "PDK_GRT_CELLS_LEF": str(p_views.get("grt_cells_lef", "")),
        "PDK_DRT_CELLS_LEF": str(p_views.get("drt_cells_lef", "")),
        "PDK_DFFE_MAP": str(p_views.get("dffe_map", "")),
        "PDK_PRIMITIVES_V": str(p_views.get("primitives_v", "")),
        "PDK_ABC_CONSTR": str(p_views.get("abc_constr", "")),
        "PDK_DRC_DECK": str(p_sig.get("drc_deck", "")),
        "PDK_LVS_DECK": str(p_sig.get("lvs_deck", "")),
        "PDK_MDP_DECK": str(p_sig.get("mdp_deck", "")),
        "PDK_IP62_DECK": str(p_sig.get("ip62_deck", "")),
        "PDK_DONT_USE_CELLS": " ".join(str(x) for x in p_syn.get("dont_use_cells", [])),
        "PDK_BUFFER_CELL": str(p_syn.get("buffer_cell", "BUF_X2")),
        "PDK_BUFFER_IN_PIN": str(p_syn.get("buffer_in_pin", "A")),
        "PDK_BUFFER_OUT_PIN": str(p_syn.get("buffer_out_pin", "Y")),
    }
    return "\n".join(f"export {k}={shlex.quote(v)}" for k, v in kv.items())


def main() -> None:
    root = repo_root()
    if "--shell" in sys.argv:
        print(export_shell_vars(root))
    else:
        design, pdk = load_design_and_pdk(root)
        print(json.dumps({"design": design, "pdk": pdk}, indent=2))


if __name__ == "__main__":
    main()
