# IHP-130 (SG13G2) PDK Setup Guide (`pdk/profiles/ihp_sg13g2.yaml`)

This profile integrates the official **IHP Open Source 130 nm SiGe BiCMOS PDK (`SG13G2`)** via Git Submodule (Option B: decoupled adapter profile).

- **Upstream Repository**: https://github.com/IHP-GmbH/IHP-Open-PDK
- **Standard Cell Library**: `sg13g2_stdcell` (`CoreSite`, `0.48 × 3.78 µm`, `1.20 V`, `Metal1–Metal5`)
- **Flow Driver**: `openroad_std` (Yosys → OpenROAD Floorplan/Placement/Routing → KLayout GDS/DRC/LVS → OpenSTA)

---

## Quick Setup (Single Target PDK Policy)

1. **Remove the default target PDK submodule (`pdk/tr1um`)** (only ONE target PDK is allowed per design repo):
   ```bash
   git submodule deinit -f pdk/tr1um
   git rm -f pdk/tr1um
   rm -rf .git/modules/pdk/tr1um
   ```

2. **Add `IHP-Open-PDK` as a Git Submodule at `pdk/ihp_sg13g2`**:
   ```bash
   git submodule add -b main https://github.com/IHP-GmbH/IHP-Open-PDK.git pdk/ihp_sg13g2
   git submodule update --init --recursive pdk/ihp_sg13g2
   ```

3. **Switch [`design.yaml`](../../design.yaml) to `ihp_sg13g2`**:
   ```yaml
   pdk:
     name: "ihp_sg13g2"
     profile: "pdk/profiles/ihp_sg13g2.yaml"

   design:
     top_module: "top"
     top_cell: "sg13g2_<your_github_user>"

   signoff:
     mdp:
       enabled: false
   ```

4. **Validate & Run the Full Pipeline**:
   ```bash
   python3 scripts/validate.py --stage pre
   bash flow/run_all.sh
   ```

---

## Notes
- For fast iteration during RTL/floorplan exploration, you may temporarily point `signoff.drc_deck` in [`pdk/profiles/ihp_sg13g2.yaml`](ihp_sg13g2.yaml) to `sg13g2_minimal.lydrc`, and switch back to `sg13g2_maximal.lydrc` for sign-off.
- Adjust `geometry.die_width_um` / `geometry.die_height_um` and `placement.place_density` in `pdk/profiles/ihp_sg13g2.yaml` to match your target macro or MPW slot size.
