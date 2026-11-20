# NEW-130E 130 nm PDK Integration Scaffold (`pdk/new130e/`)

This directory defines the drop-in contract for the target **130 nm CMOS foundry PDK (NEW-130E)** on the OpenSUSI × Google AI-Assisted Chip Design Platform.

Until the NEW-130E foundry deliverables are installed, run end-to-end experiments with the active PoC profile `pdk.name: "tr1um"` in [`design.yaml`](../../design.yaml).

## Foundry Drop-In Checklist

Populate the following artifacts under `pdk/new130e/` and update [`pdk.yaml`](pdk.yaml):

1. **Standard Cell Library (`libs.ref/stdcell/`)**
   - Timing / Power Liberty (`.lib`): TT / SS / FF corners (`1.8 V`, etc.)
   - Abstract Layout (`.lef`): cell pins, obstructions, core site definition
   - Physical GDSII (`.gds`) & LVS SPICE (`.spice` / `.cdl`)
   - Behavioral Verilog (`verilog/*.v`) for gate-level simulation
2. **Technology & OpenROAD Views (`libs.tech/openroad/`, `libs.tech/yosys/`)**
   - Tech LEF (metal stack, routing pitch, via definitions, manufacturing grid)
   - RC parasitic extraction (`rcx_rules` / `set_layer_rc`) for OpenSTA
   - Yosys techmap / latch / tie-cell mapping (`dffe_map.v`, `abc.constr`)
3. **MPW Padframe / Slot Boundary (`libs.ref/io/`)**
   - Official MPW slot die size, core opening, seal ring, ESD/IO pad GDS & SPICE
   - Pin coordinates and power ring attachment points
4. **Sign-off Rule Decks (`libs.tech/klayout/` or Magic/Netgen)**
   - Batch DRC deck (`run.drc`)
   - Batch LVS deck (`run.lvs`)
   - Optional Mask Data Preparation / density fill deck

Once populated, switch `pdk.name: "new130e"` in `design.yaml` and run `python3 scripts/validate.py --stage pre` to verify compliance.
