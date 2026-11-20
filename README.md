# OpenSUSI × Google AI-Assisted Chip Design Platform — MPW Design Template (`NEW-130E_MPW_template`)

> Language: **English** | [日本語 (README-JP.md)](README-JP.md)

Standardized **GitHub-to-Silicon** design repository template for the OpenSUSI × Google AI-Assisted Chip Design Platform.

- **Target Production PDK**: **NEW-130E** (new 130 nm CMOS foundry PDK — adapter profile in [`pdk/profiles/new130e.yaml`](pdk/profiles/new130e.yaml), guide in [`pdk/profiles/new130e.md`](pdk/profiles/new130e.md))
- **Supported Open 130 nm PDKs (Git Submodule)**:
  - **IHP-130 (`SG13G2`)** — [`pdk/profiles/ihp_sg13g2.yaml`](pdk/profiles/ihp_sg13g2.yaml) / [`ihp_sg13g2.md`](pdk/profiles/ihp_sg13g2.md) (https://github.com/IHP-GmbH/IHP-Open-PDK)
  - **SkyWater `SKY130`** — [`pdk/profiles/sky130.yaml`](pdk/profiles/sky130.yaml) / [`sky130.md`](pdk/profiles/sky130.md) (https://github.com/google/skywater-pdk)
- **Active PoC PDK**: OpenSUSI **TR-1um** (`1.0 µm` CMOS, 2-Metal `M1`/`M2`, `5.0 V`, 16-pin `OSS_FRAME_GIO` — adapter profile in [`pdk/profiles/tr1um.yaml`](pdk/profiles/tr1um.yaml), see [`pdk/README.md`](pdk/README.md) for the **Single Target PDK** Submodule policy)

---

## 1. Repository Structure & Policy

Standardized directory layout for the OpenSUSI × Google AI-Assisted Chip Design Platform:

```text
NEW-130E_MPW_template/
├── README.md                 # English documentation
├── README-JP.md              # Japanese documentation (日本語版)
├── AGENTS.md                 # AI Agent common contract (Prefix / Fixed)
├── GEMINI.md                 # Gemini / Vertex AI specific instructions (Prefix / Fixed)
├── design.yaml               # Unified project / PDK / target / CI config (Prefix schema)
├── pdk/                      # Single target PDK (Git Submodule) + decoupled profiles
│   ├── README.md             # Single-PDK policy & Git Submodule setup guide
│   ├── profiles/             # Template-managed PDK adapter profiles (tr1um, ihp_sg13g2, sky130, new130e)
│   └── tr1um/                # Default target PDK Git Submodule (OpenSUSI/TR-1um @ dev)
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
│   ├── tr1um_v2spice.py      # Generic TR-1um Verilog + DEF -> LVS SPICE (.cir) builder
│   ├── openroad_def2gds.py   # Generic openroad_std DEF -> GDSII converter (IHP-130/SKY130/NEW-130E)
│   ├── openroad_v2spice.py   # Generic openroad_std Verilog -> LVS SPICE (.cir) builder
│   └── prepare_sky130.py     # Helper to build merged SKY130 views from google/skywater-pdk submodule
├── .github/
│   ├── actions/              # Reusable composite actions (checkout-pdk, setup-klayout)
│   └── workflows/
│       └── design-ci.yml     # CI/CD + GCP dispatch + MPW sign-off workflow (Prefix / Fixed)
├── docs/
│   ├── design-spec.md        # Designer target specification (input to Gemini)
│   └── ai-design-guide.md    # AI-Assisted Chip Design workflow guide
├── reference/                # Designer reference materials (datasheets, specs, papers)
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
- `klayout` (`0.30.13` recommended; auto-detected on Linux PATH and macOS `/Applications/klayout.app`)

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

---

## 3. Designer Workflow & Prompting Gemini

### 3.1 Clone & Prepare Your Design Repository

1. **Clone with Submodule**:
   ```bash
   git clone --recurse-submodules <YOUR_REPO_URL>
   ```
   *(To switch the target PDK from default `tr1um` to `ihp_sg13g2`, `sky130`, or `new130e`, follow [`pdk/README.md`](pdk/README.md) — select **one** target PDK per repository.)*
2. **Edit Designer Inputs**:
   - [`design.yaml`](design.yaml): Update `project` metadata (`name`, `github_user`), `design.top_cell`, active `pdk`, and PPA `targets` (keep all schema keys intact).
   - [`docs/design-spec.md`](docs/design-spec.md): Write your target functional specification, I/O pinout, and acceptance criteria.
   - [`reference/`](reference/README.md): *(Optional)* Place reference papers, datasheets, block diagrams, protocol specs, or golden test vectors.

### 3.2 Prompting Gemini / Antigravity (Pattern A / B / C)

Because Gemini / Antigravity automatically loads [`AGENTS.md`](AGENTS.md) and [`GEMINI.md`](GEMINI.md), you do **not** need to repeat EDA pipeline steps, DRC/LVS rules, or governance constraints in your prompt.

- **Pattern A — Implement & Sign Off from `docs/design-spec.md` (Standard)**:
  > Using `docs/design-spec.md` and the materials in `reference/`, implement `rtl/top.v`, `constraints/pin_order.cfg`, `constraints/timing.sdc`, and `verification/testbench/tb_top.v` for the active PDK, then run `flow/run_all.sh` and iterate until all sign-off gates (RTL/GL Sim, P&R, Precheck, DRC, LVS, STA) PASS.

- **Pattern B — Co-Design the Specification with Gemini First**:
  > Review the materials placed in `reference/` and draft a chip specification in `docs/design-spec.md` that fits within the active PDK's physical limits (pin count and cell budget). Wait for my approval before implementing the RTL and running sign-off.

- **Pattern C — Iterative PPA Optimization & Debugging**:
  > Inspect `output/reports/summary.json`, pipeline the critical path to improve estimated Fmax above 20 MHz (or reduce cell count below target), and verify that all sign-off gates PASS again.

### 3.3 Sign-Off & MPW Submission

Once your specification (`docs/design-spec.md`), reference materials (`reference/`), and RTL/constraints/testbench are ready:

1. **Run the End-to-End Sign-Off Pipeline** (choose one of three execution modes):
   - **Local (or via Gemini / Antigravity)**:
     ```bash
     bash flow/run_all.sh
     ```
   - **Docker Container (`OpenSUSI-EDA-Container`, no local EDA install required)**:
     ```bash
     docker run --rm --platform linux/amd64 -v "$PWD:/work" opensusi-eda:v0.1.0 bash flow/run_all.sh
     ```
   - **GitHub Actions / GCP Cloud Batch**:
     ```bash
     git add design.yaml docs/design-spec.md reference/ rtl/ constraints/ verification/
     git commit -m "feat: implement design and constraints"
     git push origin main
     ```
     Push triggers [`.github/workflows/design-ci.yml`](.github/workflows/design-ci.yml). For full cloud sign-off on GCP Cloud Batch, run `workflow_dispatch` with `execution_backend: gcp-batch` (or set `gcp.enabled: true` in `design.yaml`).

2. **Verify Sign-Off Telemetry (`output/reports/summary.json`)**:
   ```bash
   cat output/reports/summary.json
   ```
   Confirm:
   - `"overall_status": "PASS"`
   - All 10 gates in `checks` (`rtl_sim`, `synth`, `gl_sim`, `floorplan`, `route`, `precheck`, `drc`, `lvs`, `mdp_ip62`, `sta`) are `"PASS"`
   - `openroad_drc == 0`, `klayout_drc_errors == 0`, `lvs_match == true`, `ip62_drc_errors == 0`, and `sta_wns_ns >= 0.0`

3. **Inspect & Submit the MPW Bundle**:
   - Optionally open `output/gds/<top_cell>.gds` in KLayout GUI for visual inspection.
   - Submit `output/package/<top_cell>_mpw_bundle.tar.gz` (verified by SHA-256 checksums in `output/package/manifest.json`) to the OpenSUSI MPW Submission Gateway.
