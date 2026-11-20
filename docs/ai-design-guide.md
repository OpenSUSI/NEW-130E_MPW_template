# AI-Assisted Chip Design Guide (`docs/ai-design-guide.md`)

This guide explains how designers collaborate with **Gemini / Vertex AI** (or compatible AI agents) on the **OpenSUSI × Google AI-Assisted Chip Design Platform** to go **from GitHub to Silicon**.

---

## 1. Platform Workflow

1. **Clone the Template**: Create a new repository from `NEW-130E_MPW_template`.
2. **Author Your Specification & Reference Materials**: Describe your chip's architecture, I/O pinout, and PPA goals in [`docs/design-spec.md`](design-spec.md), place any supporting datasheets/papers/diagrams in [`reference/`](../reference/README.md), and update project metadata in [`design.yaml`](../design.yaml).
3. **Collaborate with Gemini**:
   - Gemini reads `GEMINI.md`, `AGENTS.md`, `design.yaml`, `pdk/profiles/<active>.yaml`, `docs/design-spec.md`, and `reference/`.
   - Gemini generates/refines `rtl/top.v`, `constraints/timing.sdc`, `constraints/pin_order.cfg`, and `verification/testbench/tb_top.v`.
4. **Run EDA Pipeline (Locally or on GCP via GitHub Actions)**:
   ```bash
   bash flow/run_all.sh
   ```
   Every commit pushed to GitHub triggers `.github/workflows/design-ci.yml`, which validates template compliance, dispatches EDA execution (GCP EDA container or runner), and runs MPW sign-off checks.
5. **Inspect Telemetry & Iterate**:
   - Inspect `output/reports/summary.json` for functional sim, cell count, utilization, STA WNS/TNS, wirelength, DRC, LVS, and IP62 status.
   - Feed bottlenecks back to Gemini to optimize RTL/constraints while keeping `flow/`, `scripts/`, `pdk/`, and `.github/` untouched.
6. **MPW Submission**:
   - Once `scripts/validate.py --stage post` passes, `scripts/package.py` builds `output/package/<top_cell>_mpw_bundle.tar.gz` with a signed-off `manifest.json` and SHA-256 checksums for the OpenSUSI Submission Gateway.

---

## 2. Migrating from TR-1um PoC to NEW-130E (130 nm)

The template isolates foundry specifics using **Option B (decoupled adapter profiles + single target PDK Git Submodule)** (see [`pdk/README.md`](../pdk/README.md)):

- **Today (PoC)**: `pdk.name: "tr1um"` (`pdk/profiles/tr1um.yaml`) runs a complete 2-metal 1 µm CMOS tapeout flow (Yosys → TR-1um TAP2 placer → OpenROAD GRT/DRT → KLayout GDS/DRC/LVS/MDP/IP62).
- **Target (130 nm Fab)**: Remove `pdk/tr1um`, mount the single target PDK repository as a Git Submodule at `pdk/new130e/`, update `pdk/profiles/new130e.yaml`, and set `pdk.name: "new130e"` / `pdk.profile: "pdk/profiles/new130e.yaml"` in `design.yaml`. All template validation, AI agent prompts (`AGENTS.md`/`GEMINI.md`), CI triggers, telemetry (`summary.json`), and packaging (`package.py`) remain unchanged.
