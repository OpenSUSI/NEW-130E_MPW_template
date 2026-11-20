#!/usr/bin/env python3
"""
Aggregates simulation, synthesis, floorplan, routing, Precheck, DRC, LVS,
MDP/IP62, and STA telemetry into output/reports/summary.json for CI & Gemini.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from config_loader import load_design_and_pdk


def count_lyrdb_violations(path: Path) -> int:
    if not path.is_file():
        return -1
    return path.read_text(encoding="utf-8", errors="replace").count("<visited>false</visited>")


def parse_detailed_route_metrics(log_path: Path) -> dict[str, int]:
    wl_um, vias, drc = 0, 0, -1
    if not log_path.is_file():
        return {"wirelength_um": wl_um, "signal_vias": vias, "openroad_drc": drc}
    text = log_path.read_text(encoding="utf-8", errors="replace")
    m_wl = re.findall(r"Total wire length\s*=\s*(\d+)\s*um", text)
    if m_wl:
        wl_um = int(m_wl[-1])
    m_via = re.findall(r"Total number of vias\s*=\s*(\d+)", text)
    if m_via:
        vias = int(m_via[-1])
    m_drc = re.findall(r"Number of violations\s*=\s*(\d+)", text)
    if m_drc:
        drc = int(m_drc[-1])
    return {"wirelength_um": wl_um, "signal_vias": vias, "openroad_drc": drc}


def parse_sta_metrics(sta_path: Path, clock_period_ns: float) -> dict[str, float | None]:
    wns, tns, worst_min = None, None, None
    if not sta_path.is_file():
        return {"sta_wns_ns": wns, "sta_tns_ns": tns, "sta_min_slack_ns": worst_min, "est_fmax_mhz": None}
    text = sta_path.read_text(encoding="utf-8", errors="replace")
    m_wns = re.search(r"wns\s+max\s+([+-]?\d+(?:\.\d+)?)|wns\s+([+-]?\d+(?:\.\d+)?)", text)
    if m_wns:
        wns = float(m_wns.group(1) or m_wns.group(2))
    m_tns = re.search(r"tns\s+max\s+([+-]?\d+(?:\.\d+)?)|tns\s+([+-]?\d+(?:\.\d+)?)", text)
    if m_tns:
        tns = float(m_tns.group(1) or m_tns.group(2))
    m_smax = re.search(r"worst slack max\s+([+-]?\d+(?:\.\d+)?)", text)
    if m_smax:
        wns_slack = float(m_smax.group(1))
    else:
        wns_slack = wns
    m_smin = re.search(r"worst slack min\s+([+-]?\d+(?:\.\d+)?)", text)
    if m_smin:
        worst_min = float(m_smin.group(1))

    est_fmax = None
    if wns_slack is not None and clock_period_ns > 0:
        min_period = clock_period_ns - wns_slack
        if min_period > 0:
            est_fmax = round(1000.0 / min_period, 2)
    return {
        "sta_wns_ns": wns,
        "sta_tns_ns": tns,
        "sta_max_slack_ns": wns_slack,
        "sta_min_slack_ns": worst_min,
        "est_fmax_mhz": est_fmax,
    }


def main() -> None:
    design, pdk = load_design_and_pdk(ROOT)
    top_module = design["design"]["top_module"]
    top_cell = design["design"]["top_cell"]
    clk_period = float(design.get("targets", {}).get("clock_period_ns", 100.0))

    logs = ROOT / "output/logs"
    rpts = ROOT / "output/reports"

    rtl_ok = (logs / "rtl_sim.log").is_file() and "PASS:" in (logs / "rtl_sim.log").read_text(errors="replace")
    gl_ok = (logs / "gl_sim.log").is_file() and "PASS:" in (logs / "gl_sim.log").read_text(errors="replace")
    syn_ok = (ROOT / "output/work" / f"{top_module}_syn.v").is_file()

    fp_data = {}
    if (rpts / "floorplan.json").is_file():
        fp_data = json.loads((rpts / "floorplan.json").read_text(encoding="utf-8"))
    fp_ok = bool(fp_data)

    route_metrics = parse_detailed_route_metrics(logs / "detailed_route.log")
    route_ok = (ROOT / "output/gds" / f"{top_cell}.gds").is_file() and route_metrics["openroad_drc"] == 0

    precheck_ok = (logs / "precheck.log").is_file() and "PRECHECK PASS" in (logs / "precheck.log").read_text(errors="replace")
    drc_err = count_lyrdb_violations(rpts / "drc.lyrdb")
    drc_ok = drc_err == 0

    lvs_text = (logs / "lvs.log").read_text(errors="replace") if (logs / "lvs.log").is_file() else ""
    lvs_match = ("Netlists match" in lvs_text or "Congratulations! Netlists match." in lvs_text) and "ERROR : Netlists don't match" not in lvs_text

    ip62_err = count_lyrdb_violations(rpts / "ip62_drc.lyrdb")
    mdp_enabled = bool(design.get("signoff", {}).get("mdp", {}).get("enabled", True))
    mdp_ok = (ip62_err == 0) if mdp_enabled else True

    sta_metrics = parse_sta_metrics(rpts / "sta.rpt", clk_period)
    sta_ok = sta_metrics["sta_wns_ns"] is None or sta_metrics["sta_wns_ns"] >= 0.0

    checks = {
        "rtl_sim": "PASS" if rtl_ok else "FAIL",
        "synth": "PASS" if syn_ok else "FAIL",
        "gl_sim": "PASS" if gl_ok else "FAIL",
        "floorplan": "PASS" if fp_ok else "FAIL",
        "route": "PASS" if route_ok else "FAIL",
        "precheck": "PASS" if precheck_ok else "FAIL",
        "drc": "PASS" if drc_ok else "FAIL",
        "lvs": "PASS" if lvs_match else "FAIL",
        "mdp_ip62": "PASS" if mdp_ok else "FAIL",
        "sta": "PASS" if sta_ok else "FAIL",
    }
    overall = "PASS" if all(v == "PASS" for v in checks.values()) else "FAIL"

    container_versions = None
    ver_file = Path("/etc/opensusi-eda-versions.json")
    if ver_file.is_file():
        try:
            container_versions = json.loads(ver_file.read_text(encoding="utf-8"))
        except Exception:
            container_versions = None

    summary = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project": design["project"]["name"],
        "pdk": pdk["name"],
        "top_module": top_module,
        "top_cell": top_cell,
        "overall_status": overall,
        "checks": checks,
        "eda_container": container_versions,
        "metrics": {
            "stdcell_count": fp_data.get("stdcell_count", 0),
            "ff_count": fp_data.get("ff_count", 0),
            "comb_count": fp_data.get("comb_count", 0),
            "utilization_pct": fp_data.get("utilization_pct", 0.0),
            "tap2_count": fp_data.get("tap2_count", 0),
            "fill3_count": fp_data.get("fill3_count", 0),
            "fill2_count": fp_data.get("fill2_count", 0),
            "fill1_count": fp_data.get("fill1_count", 0),
            "net_count": fp_data.get("net_count", 0),
            **route_metrics,
            "klayout_drc_errors": drc_err,
            "lvs_match": lvs_match,
            "ip62_drc_errors": ip62_err,
            "clock_period_ns": clk_period,
            **sta_metrics,
        },
    }

    out_path = rpts / "summary.json"
    out_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if overall != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()
