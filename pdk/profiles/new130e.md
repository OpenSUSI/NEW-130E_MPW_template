# NEW-130E 130 nm PDK Integration Guide (`pdk/profiles/new130e.yaml`)

This profile defines the adapter contract (Option B: profile-decoupled Submodule) for the target **130 nm CMOS foundry PDK (NEW-130E)** on the OpenSUSI × Google AI-Assisted Chip Design Platform.

Until the NEW-130E foundry PDK repository is mounted as a Git Submodule under `pdk/new130e/`, run end-to-end experiments with the active PoC profile `pdk.name: "tr1um"` (`pdk/profiles/tr1um.yaml`) in [`design.yaml`](../../design.yaml).

## Foundry Submodule Drop-In Checklist

Per the **Single Target PDK Policy** (see [`pdk/README.md`](../README.md)), select **one** target PDK per design repository:

1. Remove the default TR-1um submodule (`git submodule deinit -f pdk/tr1um && git rm -f pdk/tr1um && rm -rf .git/modules/pdk/tr1um`) and mount the NEW-130E PDK repository as a Git Submodule at `pdk/new130e`:
   ```bash
   git submodule add -b <branch_or_tag> <NEW130E_PDK_REPO_URL> pdk/new130e
   ```
2. Map the following foundry artifacts in [`pdk/profiles/new130e.yaml`](new130e.yaml):
   - **Standard Cell Library (`libs.ref/stdcell/`)**:
     - Timing / Power Liberty (`.lib`): TT / SS / FF corners (`1.8 V`, etc.)
     - Abstract Layout (`.lef`): cell pins, obstructions, core site definition
     - Physical GDSII (`.gds`) & LVS SPICE (`.spice` / `.cdl`)
     - Behavioral Verilog (`verilog/*.v`) for gate-level simulation
   - **Technology & OpenROAD Views (`libs.tech/openroad/`, `libs.tech/yosys/`)**:
     - Tech LEF (metal stack, routing pitch, via definitions, manufacturing grid)
     - RC parasitic extraction (`rcx_rules` / `set_layer_rc`) for OpenSTA
     - Yosys techmap / latch / tie-cell mapping (`dffe_map.v`, `abc.constr`)
   - **MPW Padframe / Slot Boundary (`libs.ref/io/`)**:
     - Official MPW slot die size, core opening, seal ring, ESD/IO pad GDS & SPICE
     - Pin coordinates and power ring attachment points
   - **Sign-off Rule Decks (`libs.tech/klayout/` or Magic/Netgen)**:
     - Batch DRC deck (`run.drc`)
     - Batch LVS deck (`run.lvs`)
     - Optional Mask Data Preparation / density fill deck
3. Update `status: "active"` in [`pdk/profiles/new130e.yaml`](new130e.yaml), switch [`design.yaml`](../../design.yaml) to:
   ```yaml
   pdk:
     name: "new130e"
     profile: "pdk/profiles/new130e.yaml"
   ```
   and run `python3 scripts/validate.py --stage pre` to verify compliance.
