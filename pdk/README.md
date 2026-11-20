# PDK Profiles (`pdk/`)

This directory provides a standardized, PDK-agnostic adapter layer for the OpenSUSI AI-Assisted Chip Design Platform.

Each target foundry process lives in its own subdirectory (`pdk/<pdk_name>/`) and exposes a uniform `pdk.yaml` contract consumed by `flow/*.sh`, `scripts/validate.py`, and CI/CD pipelines.

## Available Profiles

| Profile | Process | Status | Purpose |
| :--- | :--- | :--- | :--- |
| [`tr1um/`](tr1um/pdk.yaml) | OpenSUSI **TR-1um** (1.0 µm CMOS, 2M, 5.0 V) | **Active (PoC)** | End-to-end working proof-of-concept using Yosys + OpenROAD + KLayout DRC/LVS/MDP/IP62 |
| [`new130e/`](new130e/pdk.yaml) | **NEW-130E** (130 nm CMOS, target fab) | **Scaffold (Target)** | Standardized 130 nm PDK integration contract ready for foundry Tech/StdCell/Sign-off drop-in |

## Switching Active PDK

Set `pdk.name` in [`design.yaml`](../design.yaml):

```yaml
pdk:
  name: "tr1um"     # Change to "new130e" once NEW-130E PDK files are populated
```

## PDK Adapter Contract

Every `pdk/<name>/pdk.yaml` defines:
1. **Technology & Geometry**: node, DBU, metal stack, core site, row pitch, die size, core bbox, frame cell names.
2. **Views**: `tech_lef`, `cells_lef` (and optional `grt_lef`/`drt_lef`), `liberty`, `stdcell_gds`, `stdcell_spice_dir`, `frame_gds`, `pad_spice`, `primitives_v`, `dffe_map`.
3. **Sign-off Decks**: `drc_deck`, `lvs_deck`, `mdp_deck`, `ip62_deck`.
4. **Padframe Pinout**: Physical pad names, edges, coordinates, and power pad assignments.
