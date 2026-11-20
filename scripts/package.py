#!/usr/bin/env python3
"""
MPW Submission Packager for OpenSUSI Submission Gateway.
Bundles signed-off GDSII, LVS netlist, MDP GDSII, reports, and design.yaml
with SHA-256 checksums into output/package/<top_cell>_mpw_bundle.tar.gz.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from config_loader import load_design_and_pdk, repo_root


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    root = repo_root()
    design, pdk = load_design_and_pdk(root)

    top_cell = design["design"]["top_cell"]
    mdp_file = design.get("signoff", {}).get("mdp", {}).get("file", "")
    summary_path = root / "output/reports/summary.json"
    if not summary_path.is_file():
        print("ERROR: output/reports/summary.json not found. Run flow/run_all.sh first.", file=sys.stderr)
        sys.exit(1)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("overall_status") != "PASS":
        print(f"ERROR: Cannot package failed sign-off (overall_status={summary.get('overall_status')})", file=sys.stderr)
        sys.exit(1)

    pkg_dir = root / "output/package"
    pkg_dir.mkdir(parents=True, exist_ok=True)

    candidates = [
        Path("design.yaml"),
        Path(design["design"]["constraints"]["pin_order"]),
        Path(design["design"]["constraints"]["sdc"]),
        Path("docs/design-spec.md"),
        Path(f"output/gds/{top_cell}.gds"),
        Path(f"output/gds/{top_cell}.cir"),
        Path(f"output/gds/{top_cell}.extracted"),
        Path("output/reports/summary.json"),
        Path("output/reports/drc.lyrdb"),
        Path("output/reports/lvs.lvsdb"),
        Path("output/reports/sta.rpt"),
    ]
    if mdp_file:
        candidates.append(Path(f"output/gds/{mdp_file}"))
        candidates.append(Path("output/reports/ip62_drc.lyrdb"))

    included = []
    for rel in candidates:
        fp = root / rel
        if fp.is_file():
            included.append({
                "path": str(rel),
                "bytes": fp.stat().st_size,
                "sha256": sha256_file(fp),
            })

    manifest = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "platform": "OpenSUSI x Google AI-Assisted Chip Design Platform",
        "project": design["project"],
        "pdk": {
            "name": pdk["name"],
            "display_name": pdk.get("display_name", pdk["name"]),
        },
        "design": {
            "top_module": design["design"]["top_module"],
            "top_cell": top_cell,
        },
        "signoff_status": summary.get("overall_status"),
        "checks": summary.get("checks", {}),
        "metrics": summary.get("metrics", {}),
        "artifacts": included,
    }

    manifest_path = pkg_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    bundle_path = pkg_dir / f"{top_cell}_mpw_bundle.tar.gz"
    with tarfile.open(bundle_path, "w:gz") as tar:
        tar.add(manifest_path, arcname=f"{top_cell}/manifest.json")
        for item in included:
            tar.add(root / item["path"], arcname=f"{top_cell}/{item['path']}")

    print(f"PACKAGED: {bundle_path} ({bundle_path.stat().st_size} bytes, {len(included)} artifacts)")
    print(f"MANIFEST: {manifest_path}")


if __name__ == "__main__":
    main()
