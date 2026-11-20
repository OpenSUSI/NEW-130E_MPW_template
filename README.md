# OpenSUSI × Google AI-Assisted Chip Design Platform — MPW Design Template (`NEW-130E_MPW_template`)

Standardized **GitHub-to-Silicon** design repository template for the OpenSUSI × Google AI-Assisted Chip Design Platform.

- **Target Production PDK**: **NEW-130E** (new 130 nm CMOS foundry PDK — adapter contract in [`pdk/new130e/`](pdk/new130e/README.md))
- **Active PoC PDK**: OpenSUSI **TR-1um** (`1.0 µm` CMOS, 2-Metal `M1`/`M2`, `5.0 V`, 16-pin `OSS_FRAME_GIO` — self-contained PoC backend in [`pdk/tr1um/`](pdk/tr1um/pdk.yaml))

---

## 1. Repository Structure & Policy

Standardized directory layout for the OpenSUSI × Google AI-Assisted Chip Design Platform:

```text
NEW-130E_MPW_template/
├── README.md
├── AGENTS.md                 # AI Agent common contract (Prefix / Fixed)
├── GEMINI.md                 # Gemini / Vertex AI specific instructions (Prefix / Fixed)
├── design.yaml               # Unified project / PDK / target / CI config (Prefix schema)
├── pdk/                      # PDK profiles (tr1um PoC active; new130e 130nm scaffold)
│   ├── tr1um/                # Self-contained TR-1um PoC LEF/LIB/GDS/SPICE/DRC/LVS/MDP
│   └── new130e/              # Target 130nm foundry PDK adapter contract
├── rtl/
│   └── top.v                 # Synthesizable RTL (PoC: 4-bit Registered ALU/Accumulator)
├── constraints/
│   ├── timing.sdc            # SDC timing constraints
│   └── pin_order.cfg         # Padframe-to-signal mapping
├── verification/
│   └── testbench/
│       └── tb_top.v          # Self-checking RTL & gate-level testbench
├── flow/
│   ├── common.sh             # Shared config/tool discovery
│   ├── synth.sh              # Stage 1: Validate + RTL Sim + Yosys + Gate-Level Sim
│   ├── floorplan.sh          # Stage 2: Floorplan + Placement + TAP/Decap fill
│   ├── place_route.sh        # Stage 3: OpenROAD GRT/DRT + Full-chip GDSII + LVS SPICE
│   ├── signoff.sh            # Stage 4: Precheck + DRC + Strict LVS + MDP/IP62 + STA
│   └── run_all.sh            # End-to-end GitHub-to-Silicon pipeline
├── scripts/
│   ├── config_loader.py      # Zero-dependency YAML & pin_order.cfg loader
│   ├── validate.py           # Template policy, schema, port-match & sign-off gate validator
│   ├── package.py            # MPW Submission Gateway bundle & SHA-256 manifest builder
│   ├── pre_check.py          # KLayout MPW GDSII Precheck (top cell, DBU, bbox, frame)
│   ├── tr1um_place.py        # Generic TR-1um TAP2-row placer & FILL3/FILL2 decap filler
│   ├── tr1um_def2gds.py      # Generic TR-1um DEF -> full-chip GDSII & OSS_FRAME router
│   └── tr1um_v2spice.py      # Generic TR-1um Verilog + DEF -> LVS SPICE (.cir) builder
├── .github/
│   ├── actions/              # Reusable composite actions (checkout-pdk, setup-klayout)
│   └── workflows/
│       └── design-ci.yml     # CI/CD + GCP dispatch + MPW sign-off workflow (Prefix / Fixed)
├── docs/
│   ├── design-spec.md        # Designer target specification (input to Gemini)
│   └── ai-design-guide.md    # AI-Assisted Chip Design workflow guide
└── output/                   # GCP / CI controlled outputs (Prefix / Fixed)
    ├── gds/
    ├── reports/
    └── logs/
```

### Governance Policy

| Item | Policy |
| :--- | :--- |
| Folder structure | **Prefix (Fixed)** |
| `GEMINI.md` / `AGENTS.md` | **Prefix (Fixed)** |
| `design.yaml` | **Prefix (Schema Fixed)** |
| `.github/` | **Prefix (Fixed)** |
| `output/` | **Prefix (GCP / CI Controlled)** |

---

## 2. Quick Start (TR-1um PoC)

### Prerequisites
- `python3` (standard library only; no `pip` packages required)
- `iverilog` / `vvp`
- `yosys`
- `openroad`
- `klayout` (`0.30.9` recommended; auto-detected on Linux PATH and macOS `/Applications/klayout.app`)

### Run Full Pipeline
```bash
bash flow/run_all.sh
```

Or run individual stages:
```bash
python3 scripts/validate.py --stage pre
bash flow/synth.sh
bash flow/floorplan.sh
bash flow/place_route.sh
bash flow/signoff.sh
python3 scripts/validate.py --stage post
python3 scripts/package.py
```

### Key Outputs
- `output/gds/<top_cell>.gds` — Full-chip sign-off GDSII (`2500 × 2500 µm` `OSS_FRAME_GIO`)
- `output/gds/<top_cell>.cir` — Hierarchical LVS reference SPICE netlist
- `output/gds/<mdp_file>` — MDP / IP62 mask-ready GDSII
- `output/reports/summary.json` — Unified PPA & sign-off telemetry for CI and Gemini
- `output/package/<top_cell>_mpw_bundle.tar.gz` — Submission bundle + `manifest.json`
