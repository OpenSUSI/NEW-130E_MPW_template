# Design Specification (`docs/design-spec.md`)

> Designer-authored target specification used by both human engineers and Gemini / AI Agents.

## 1. Overview

- **Design Name**: `poc_alu4` (`top`)
- **Target Platform**: OpenSUSI × Google AI-Assisted Chip Design Platform
- **Active PoC PDK**: OpenSUSI **TR-1um** (`1.0 µm` CMOS, 2-Metal `M1`/`M2`, `5.0 V`, 16-pin `OSS_FRAME_GIO`, `2500 × 2500 µm` die)
- **Target Production PDK**: **NEW-130E** (`130 nm` CMOS)

This reference design implements a **4-bit Registered ALU & Accumulator** to validate the complete GitHub-to-Silicon pipeline (Template Validation → RTL Sim → Yosys Synthesis → Gate-Level Sim → Placement & Decap Fill → OpenROAD Routing → Full-Chip GDSII Assembly → Precheck / KLayout DRC / Strict LVS / MDP / IP62 DRC / STA → MPW Packaging).

---

## 2. Functional Specification

### Internal State
- `acc[3:0]`: 4-bit accumulator register (drives `out_data[3:0]` directly for minimal output delay)
- `carry`: 1-bit carry / borrow / shift-out flag register

### Reset & Enable Behavior
- **Asynchronous Active-Low Reset (`rst_n == 0`)**:
  - `acc <= 4'h0`
  - `carry <= 1'b0`
- **Clocked Update (`posedge clk` when `rst_n == 1`)**:
  - If `en == 0`: Hold `acc` and `carry` unchanged.
  - If `en == 1`: Execute operation selected by `op[1:0]`:

| `op[1:0]` | Mnemonic | Operation |
| :---: | :---: | :--- |
| `2'b00` | `ADD` | `{carry, acc} <= {1'b0, acc} + {1'b0, in_data}` |
| `2'b01` | `SUB` | `{carry, acc} <= {1'b0, acc} - {1'b0, in_data}` (`carry = 1` on borrow) |
| `2'b10` | `XOR` | `acc <= acc ^ in_data`; `carry <= 1'b0` |
| `2'b11` | `ROL` | `{carry, acc} <= {acc[3], acc[2:0], in_data[0]}` (rotate/shift left with LSB inject) |

---

## 3. Pinout (`OSS_FRAME_GIO` 16-Pin Package)

Defined authoritatively in [`constraints/pin_order.cfg`](../constraints/pin_order.cfg):

| Pad | Edge | Signal | Direction | Description |
| :---: | :---: | :--- | :---: | :--- |
| `P1` | North | `clk` | `IN` | System clock |
| `P2` | North | `op[0]` | `IN` | Operation select bit 0 |
| `P3` | West | `in_data[3]` | `IN` | Input operand bit 3 (MSB) |
| `P4` | West | `in_data[2]` | `IN` | Input operand bit 2 |
| `P5` | West | `in_data[1]` | `IN` | Input operand bit 1 |
| `P6` | West | `in_data[0]` | `IN` | Input operand bit 0 (LSB) |
| `P7` | South | `rst_n` | `IN` | Asynchronous active-low reset |
| `P8` | South | `VSS` | `POWER` | Ground (`0.0 V`) |
| `P9` | South | `en` | `IN` | Operation enable (Active-High) |
| `P10` | South | `carry` | `OUT` | Registered carry / borrow / shift-out |
| `P11` | East | `out_data[0]` | `OUT` | Registered accumulator bit 0 |
| `P12` | East | `out_data[1]` | `OUT` | Registered accumulator bit 1 |
| `P13` | East | `out_data[2]` | `OUT` | Registered accumulator bit 2 |
| `P14` | East | `out_data[3]` | `OUT` | Registered accumulator bit 3 |
| `P15` | North | `op[1]` | `IN` | Operation select bit 1 |
| `P16` | North | `VDD` | `POWER` | Power supply (`5.0 V` on TR-1um) |

---

## 4. Physical & PPA Targets (TR-1um PoC)

| Metric | Target |
| :--- | :--- |
| Clock Period / Frequency | `<= 100.0 ns` (`>= 10.0 MHz`) |
| Standard Cell Count | `<= 600` cells |
| Core Logic Utilization | `<= 80.0%` |
| OpenROAD / KLayout DRC | `0` violations |
| KLayout LVS (Strict Ports) | `Match` |
| MDP / IP62 Mask DRC | `0` violations |
