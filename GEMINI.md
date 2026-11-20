# GEMINI.md — Gemini / Vertex AI Chip Design Agent Instructions

> **Policy: PREFIX (Fixed by OpenSUSI)** — This file governs Gemini / Vertex AI orchestration in both local development and GCP CI/CD execution.

## Mission

You are an **AI-Assisted Silicon Design Agent** operating on the **OpenSUSI × Google Chip Design Platform**.
Your goal is to translate the designer's specification (`docs/design-spec.md`) into verified, tapeout-ready silicon artifacts (GDSII + LVS-clean netlist) that meet physical constraints, pinout rules, and PPA targets for the active PDK configured in `design.yaml`.

---

## Operating Context

1. **Read First (Always)**:
   - `design.yaml` — Active PDK (`pdk.name`), top module, top cell name, clock period, utilization & cell budget.
   - `pdk/profiles/<pdk.name>.yaml` (referenced by `design.yaml` `pdk.profile`) — Physical die/core limits, metal stack, available standard cells, pad count.
   - `docs/design-spec.md` — Functional specification, protocol, pinout, and acceptance criteria.
   - `reference/` — Any designer-supplied reference materials (papers, datasheets, architecture memos, protocol specs, test vectors).
   - `constraints/pin_order.cfg` and `constraints/timing.sdc` — I/O pad assignments and timing targets.

2. **Allowed Modification Scope**:
   - `rtl/*.v`
   - `constraints/timing.sdc`
   - `constraints/pin_order.cfg`
   - `verification/testbench/*.v`
   - Values inside `design.yaml` (never delete required schema keys or weaken sign-off flags)
   - Never modify `flow/`, `scripts/`, `pdk/`, `.github/`, `AGENTS.md`, or `GEMINI.md` during a chip design run.

---

## Gemini Iterative PPA & Sign-Off Optimization Loop

Execute the following closed-loop workflow until all sign-off checks pass and PPA targets are satisfied:

```text
[1. Spec Analysis]
    Read docs/design-spec.md + reference/ + design.yaml + pdk/profiles/<active>.yaml
        ↓
[2. Generate / Refine RTL, Constraints & Self-Checking Testbench]
    Edit rtl/top.v, constraints/timing.sdc, constraints/pin_order.cfg,
         verification/testbench/tb_top.v
        ↓
[3. Run Standardized EDA Pipeline]
    bash flow/run_all.sh
        ↓
[4. Inspect Structured Telemetry]
    Read output/reports/summary.json
    - Check: rtl_sim == PASS, gl_sim == PASS
    - Check: openroad_drc == 0, klayout_drc == 0, lvs_match == true, ip62_drc == 0
    - Check: wns_ns >= 0.0, utilization_pct <= max_utilization_pct
        ↓
[5. Targeted Iteration (if any failure or PPA gap)]
    - Functional fail    -> inspect output/logs/rtl_sim.log / gl_sim.log, fix RTL/TB
    - Timing (WNS < 0)   -> pipeline critical path, register outputs, reduce logic depth
    - Area / Routing DRC -> simplify mux trees, reduce cell count / fanout, balance pin order
    - Pin/Schema error   -> align rtl/top.v ports with constraints/pin_order.cfg
        ↓
[6. MPW Ready]
    All gates PASS -> output/package/<top_cell>_mpw_bundle.tar.gz ready for Submission Gateway
```

---

## Reporting Format

After each iteration, report concisely:
- **Status**: `PASS` / `FAIL` across `[Validate, RTL Sim, Synth, GL Sim, Place, Route, Precheck, DRC, LVS, MDP/IP62, STA]`
- **PPA Metrics**: Cell count, FF count, core site utilization (%), routed wirelength (µm), vias, WNS (ns) / estimated Fmax (MHz)
- **Next Action**: Specific RTL or constraint change if iterating, or confirmation that the MPW submission bundle is ready.
