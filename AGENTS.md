# AGENTS.md — Common AI Agent Contract (OpenSUSI AI-Assisted Chip Design Platform)

This repository follows the standardized **OpenSUSI × Google AI-Assisted Chip Design Platform** template (`NEW-130E_MPW_template`). All AI coding agents (Gemini, Antigravity, CLI agents, etc.) MUST obey the governance policy and verification loop defined below.

---

## 1. Template Governance Policy (Prefix / Fixed vs. Designer Workspace)

Per OpenSUSI MPW submission rules, certain paths are **Prefix (Fixed / Platform-Managed)** so that GCP CI/CD, MPW Precheck, and MPW Aggregation can process every designer's repository uniformly.

| Path | Policy | Agent Permission |
| :--- | :--- | :--- |
| Top-level folder structure | **Prefix (Fixed)** | Do NOT rename, remove, or reorganize standard folders |
| `AGENTS.md`, `GEMINI.md` | **Prefix (Fixed)** | Read-only for chip designers / design agents |
| `design.yaml` | **Prefix (Schema Fixed)** | Edit project/design values only; never break required keys |
| `.github/` | **Prefix (Fixed)** | Do NOT modify CI/CD or sign-off gate workflows |
| `flow/`, `scripts/`, `pdk/` | **Platform-Managed** | Do NOT alter sign-off rules or bypass DRC/LVS/Precheck |
| `output/` | **GCP / CI Controlled** | Never hand-edit outputs; generated only by `flow/*.sh` |
| `docs/design-spec.md` | **Designer Workspace** | Source of truth for functional & PPA requirements |
| `rtl/` | **Designer / AI Workspace** | Edit synthesizable Verilog / SystemVerilog here |
| `constraints/` | **Designer / AI Workspace** | Edit `timing.sdc` and `pin_order.cfg` within PDK limits |
| `verification/testbench/` | **Designer / AI Workspace** | Add/update self-checking testbenches here |

---

## 2. Mandatory Design & Verification Loop

Before declaring any RTL or constraint change complete, an agent MUST execute and pass:

1. **Template & Schema Validation**:
   ```bash
   python3 scripts/validate.py --stage pre
   ```
2. **End-to-End Flow (`flow/run_all.sh`)**:
   - `flow/synth.sh`: RTL simulation (`iverilog`) → Yosys synthesis → Gate-level simulation (`iverilog -DGATE_LEVEL`)
   - `flow/floorplan.sh`: Floorplan, placement, TAP insertion, active decap fill (`FILL1 = 0` on TR-1um)
   - `flow/place_route.sh`: OpenROAD Global Route → Detailed Route (`0` OpenROAD DRC) → Full-chip GDSII + LVS SPICE
   - `flow/signoff.sh`: MPW Precheck → KLayout DRC (`0` violations) → KLayout LVS (`Match`, strict ports) → MDP & IP62 DRC (`0` violations) → STA summary
3. **Post-Signoff Gate & Packaging**:
   ```bash
   python3 scripts/validate.py --stage post
   python3 scripts/package.py
   ```
4. **Inspect Machine-Readable Metrics**:
   Read `output/reports/summary.json` and confirm `"overall_status": "PASS"` along with PPA metrics (`cell_count`, `utilization_pct`, `wns_ns`, `tns_ns`, `drc_errors`, `lvs_match`, `ip62_drc_errors`).

---

## 3. Synthesizable RTL Rules

- Use clean, portable **Verilog-2001** (or Yosys-supported SystemVerilog) with a single top module matching `design.yaml` (`design.top_module`).
- Avoid latches, combinational loops, `initial` blocks for hardware reset, tri-state internals, and unsynthesizable delays (`#`) in `rtl/`.
- Prefer synchronous design with a single clock (`clk`) and explicit reset (`rst_n` active-low maps cleanly to `DFFRB` / `MUXDFFRB` on TR-1um).
- Every top-level module port MUST appear in `constraints/pin_order.cfg` with matching bit-width and direction (`IN` / `OUT`).
- Never waive, mask, or skip DRC, LVS, Precheck, or testbench failures.
