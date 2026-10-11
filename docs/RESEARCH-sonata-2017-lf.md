# CAN Bus Data: 2017 Hyundai Sonata Limited (LF) via OBD-II — Research Report

## Summary
A 2017 Sonata Limited (LF, 2.4L GDI, no ADAS) exposes its full chassis/powertrain CAN broadcast set on the OBD-II port (pins 6/14, 500 kbps, 11-bit IDs) with no gateway filtering of the messages a DIY LDW/FCW system needs. comma.ai's `opendbc/dbc/hyundai_2015_ccan.dbc` decodes it — the file was validated against a real 2017 LF Sonata. openpilot itself is **not** usable on this car (no SCC radar / LKAS camera, so it can't fingerprint as `HYUNDAI_SONATA_LF` and has no supported-package entry), but openpilot's carstate code confirms exactly which signals the platform decodes. Yaw rate, lateral accel, analog brake pressure, and radar tracks are the gaps; everything else on the mission's signal list is available.

Conventions below: **[verified live]** = read from the actual file/page content on 2026-10-02. **[index]** = from search-result snippets. **[inferred]** = synthesis, labeled as such.

## (A) Applicable DBC / openpilot files

| File | URL | Role |
|---|---|---|
| `opendbc/dbc/hyundai_2015_ccan.dbc` | https://github.com/commaai/opendbc/blob/master/opendbc/dbc/hyundai_2015_ccan.dbc | **Primary DBC for this car.** Chassis/powertrain CAN for 2015-era Hyundai/Kia; validated against a 2017 LF Sonata **[verified live; index: PR #732]** |
| `opendbc/dbc/hyundai_2015_mcan.dbc` | (same repo, `opendbc/dbc/` folder) | Multimedia CAN — not needed for LDW/FCW **[index: listed in third-party CREDITS as Hyundai/Kia file]** |
| `opendbc/dbc/generator/hyundai/hyundai_can.dbc` | https://github.com/commaai/opendbc/blob/master/opendbc/dbc/generator/hyundai/hyundai_can.dbc | Source for the generated `hyundai_can_generated` DBC that current openpilot uses for `HYUNDAI_SONATA_LF`; same legacy message layout **[verified live]** |
| `opendbc/car/hyundai/carstate.py` | https://github.com/commaai/opendbc/blob/master/opendbc/car/hyundai/carstate.py | Shows exactly which signals openpilot reads per message (wheel speeds, SAS angle/rate, blinkers, brake, gas, gear, cruise buttons) **[verified live]** |
| `opendbc/car/hyundai/values.py` (`HYUNDAI_SONATA_LF`, lines 526–534) | https://github.com/commaai/opendbc/blob/master/opendbc/car/hyundai/values.py | Platform config: "Hyundai Sonata 2018-19", Hyundai E harness, flags `UNSUPPORTED_LONGITUDINAL | TCU_GEARS`, DBC `hyundai_can_generated` **[verified live]** |
| `opendbc/car/hyundai/fingerprints.py` (`CAR.HYUNDAI_SONATA_LF`, lines 464–488) | https://github.com/commaai/opendbc/blob/master/opendbc/car/hyundai/fingerprints.py | Fingerprint requires SCC radar FW (`0x7d0`, `LF__ SCC F-CUP`) + LKAS camera FW (`0x7c4`, `LFF LKAS AT USA LHD`) + ABS ESC FW **[verified live]** |
| `opendbc/safety/modes/hyundai.h` (`HYUNDAI_COMMON_RX_CHECKS`) | https://github.com/commaai/opendbc/blob/master/opendbc/safety/modes/hyundai.h | Panda safety layer's expected RX frequencies per CAN ID (the only documented rates) **[verified live]** |
| `opendbc/docs/CARS.md` | https://github.com/commaai/opendbc/blob/master/docs/CARS.md | Official support list: "Hyundai Sonata 2018-19, Smart Cruise Control (SCC), Upstream". No 2015–2017 Sonata rows **[verified live]** |

**openpilot support verdict:** openpilot has the `HYUNDAI_SONATA_LF` car code, fingerprint, carstate and (no-longitudinal) car controller, but official support is **2018–2019 Sonata with SCC only** (CARS.md **[verified live]**; values.py docs name "Hyundai Sonata 2018-19" **[verified live]**). The target car has no ADAS, so: no fingerprint match, no support entry, and openpilot cannot run on it. The DBC + carstate signal decoding is still directly reusable for a passive Jetson sniffer.

## (B) Signal-by-signal table (from `hyundai_2015_ccan.dbc`, verified live)

All IDs are 11-bit. DLC = OBD-II pins 6/14, 500 kbps. Rates marked † are from the panda safety RX checks (`hyundai.h`) — comma's documented expected frequencies for these exact CAN IDs on Hyundai CAN cars; all other rates are **not documented in opendbc** and should be measured on the car (e.g. `candump` timestamps).

| # | Signal | Message | CAN ID (hex / dec) | Signal detail in DBC | Typical rate |
|---|---|---|---|---|---|
| 1 | Vehicle speed | CLU11 | **0x4F1** / 1265 | `CF_Clu_Vanz`: bits 8\|9, factor 0.5, km/h **or** mph per `CF_Clu_SPEED_UNIT` (bit 17; 0 = metric) | 50 Hz † |
| 2 | Wheel speeds FL/FR/RL/RR | WHL_SPD11 | **0x386** / 902 | `WHL_SPD_FL/FR/RL/RR`: bits 0/16/32/48\|14, factor 0.03125 km/h. Has 4-bit alive counter + 4-bit checksum nibbles | 100 Hz † |
| 3 | Steering angle | SAS11 | **0x2B0** / 688 | `SAS_Angle`: bits 0\|16 signed, factor 0.1 deg | not documented — measure |
| 4 | Steering rate | SAS11 | **0x2B0** / 688 | `SAS_Speed`: bits 16\|8, factor 4.0 deg/s | not documented — measure |
| 5 | Brake lights | TCS13 | **0x394** / 916 | `BrakeLight`: bit 11 | 100 Hz † |
| 6 | Brake pedal (driver braking) | TCS13 | **0x394** / 916 | `DriverBraking`: bit 55; `DriverOverride`: bits 45\|2, `== 2` means driver braking (openpilot's `brakePressed` condition) | 100 Hz † |
| 7 | Brake pressure (analog) | — | — | **Not decoded** (see §D) | — |
| 8 | Turn signals L/R | CGW1 | **0x541** / 1345 | `CF_Gway_TurnSigLh`: bits 19\|2; `CF_Gway_TurnSigRh`: bits 62\|2 (lamp states; openpilot thresholds at 50% duty). Also `CF_Gway_TSigLHSw/RHSw` (bits 42/41, stalk switches), `CF_Gway_HazardSw` (bits 33\|2) | not documented — measure |
| 9 | Gas pedal | EMS12 / EMS16 | **0x329** / 809; **0x260** / 608 | **Primary:** `PV_AV_CAN` in EMS12 (bits 48\|8, factor 0.3906 → %). `BRAKE_ACT` bits 32\|2 also on EMS12. EMS16 `CF_Ems_AclAct` (bits 62\|2) is boolean only. EMS15 `FA_PV_CAN` (0x547) often absent on OBD | 100 Hz † |
| 10 | Gear (PRNDL) | TCU12 / TCU11 | **0x112** / 274; **0x111** / 273 | Sonata LF is `TCU_GEARS`: prefer `CUR_GR` (TCU12 bits 8\|4; 0=P, 14=R, 1–8=D) or `G_SEL_DISP` (TCU11 bits 8\|4; LVR-style 0/7/6/5). LVR11/LVR12 are fallbacks | not documented — measure |
| 11 | Cruise state | CLU11 / EMS16 | 0x4F1 / 0x260 | Buttons: `CF_Clu_CruiseSwState` (0\|3), `CF_Clu_CruiseSwMain` (bit 3) in CLU11; lamps `CRUISE_LAMP_M/S` (bits 25/26) in EMS16. No SCC state (no SCC11/12 on this car) | 50 Hz † (CLU11) |
| 12 | Yaw rate | — | — | **Not decoded** (see §D) | — |

Bonus signals in the same DBC useful for fusion/sanity: `aBasis` longitudinal accel (TCS13 0x394, 0.01 m/s²), `StandStill` (TCS13 bit 47), `PBRAKE_ACT` parking brake (TCS13 bit 53), `WHL_PUL_*` pulse counts + `WHL_DIR_*` direction (WHL_PUL11 0x387), `CR_Mdps_StrAng` second steering-angle source (MDPS11 0x381), `CR_Mdps_StrColTq` steering torque (MDPS12 0x251, 50 Hz †), ABS/EBD status (ABS11 0x38A), odometer (CLU12 0x5B0).

## (C) Gateway / bus-access verdict (2017 model year)

**Verdict: YES — the OBD-II port exposes raw, unfiltered C-CAN broadcast traffic. No gateway blocks the messages in §B.**

- Bus: chassis CAN ("C-CAN"), 11-bit IDs, **500 kbps**, DLC pins 6 (CAN-H) / 14 (CAN-L). (500 kbps is the ISO 15765 11-bit HS-CAN rate **[index]** and the panda/comma default **[index]**; openpilot operates on this platform at that rate. Confirm on the car — try 500k first.)
- Evidence chain:
  1. comma.ai reverse-engineered the entire `hyundai_2015_ccan.dbc` with its standard panda-on-OBD-II + Cabana workflow **[inferred]**; a 2017 LF Sonata owner validated the DBC against their car's CAN **[index: opendbc PR #732]**.
  2. openpilot's `HYUNDAI_SONATA_LF` port reads WHL_SPD11/SAS11/TCS13/CLU11/CGW1 from bus 0 through the Hyundai E harness on 2018–19 Sonatas **[index: openpilot PR #19915; verified live: carstate.py]** — bus 0 on comma hardware is the OBD-II-port CAN.
  3. The panda is an OBD-II dongle "capable of dumping the full contents of the busses" **[index: panda README]**; ECU firmware queries (fingerprinting) also go through the OBD-II port **[index: openpilot Fingerprinting wiki]**.
  4. A 2018 Sonata 2.0T Limited ran openpilot and fingerprinted as Sonata LF **[index: openpilot PR #21823]**.
- Practical notes: listen-only (passive) sniffing is safe; do **not** transmit on the bus. ECUs sleep with ignition off — capture with ignition on. The M-CAN (infotainment) DBC exists separately and is irrelevant here.

## (D) Gaps and fallbacks

| Gap | Detail | Recommended fallback |
|---|---|---|
| No radar / no ADAS ECUs | Car has no SCC radar or LKAS camera; LKAS11 (0x340), LKAS12, SCC11/12, FCA11 will be **absent** from the bus | FCW must be vision-only from the Jetson camera; there is no CAN object data to fuse |
| Yaw rate not decoded | No ESP12/yaw message in `hyundai_2015_ccan.dbc` (**[verified live]** — file has no yaw/lateral-accel signal) | Derive yaw rate from `SAS_Angle` + wheel-speed via kinematic bicycle model, or use a Jetson-side IMU. (0x145 ESP12 likely exists on the wire — standard Hyundai ESC message — but is undecoded; DIY reverse-engineering possible, **[inferred]**) |
| Lateral acceleration not decoded | Same as above | Jetson IMU, or derive from yaw rate × speed |
| Analog brake pressure/pedal position | Only binary-ish signals: `BrakeLight`, `DriverBraking`, `DriverOverride` in TCS13 0x394 **[verified live]** | Use `DriverOverride == 2` / `BrakeLight` for brake reaction in FCW; no analog CAN fallback exists (J1979 has no brake-pedal PID either) |
| Gear enum values | Prefer TCU11/TCU12 built-in maps; LVR11 has no VAL_ table **[verified live]** | If labels wrong, run `calibrate_gear` watching TCU11/TCU12 and write `gear_map.json` |
| Broadcast rates | Not in either DBC (no `GenMsgCycleTime`) **[verified live]** | Use §B † rates as starting expectations; measure the rest with `candump` timestamps on the car |
| Vehicle-speed unit | `CF_Clu_Vanz` is km/h or mph depending on cluster setting | Read `CF_Clu_SPEED_UNIT` (0 = metric) or just use WHL_SPD11 (always km/h) |
| J1979 PID 0x0D | Works as a fallback (diagnostic access via OBD-II is proven by fingerprinting), but polling is slow (~10–50 Hz shared) | Prefer broadcast `WHL_SPD11`/`CLU11` at 50–100 Hz; keep PID 0x0D only as a sanity check |

## (E) Trim / model-year gotchas

- **2015–2017 vs 2018–2019:** The LF chassis CAN layout (§B) is shared across 2015–2019 — the DBC was validated on a 2017 **[index: PR #732]**. 2018+ facelift cars *with the Ultimate/SCC package* additionally broadcast SCC11 (0x420), SCC12 (0x421), camera LKAS11 (0x340) and FCA11 — none of which exist on the user's car. openpilot support is 2018–19 SCC-only **[verified live: CARS.md, values.py]**; there is no official support for any 2015–2017 Sonata.
- **US vs other markets:** The fingerprint DB shows USA-LHD camera FW variants (`LFF LKAS AT USA LHD`) **[verified live]**; the DBC itself is market-agnostic except `CF_Clu_SPEED_UNIT` (km/h vs mph cluster setting) and engine EMS variants. All §B chassis signals come from ABS/ESC/SAS/MDPS/BCM/CLU and are engine-agnostic.
- **Limited vs SE/SEL:** No difference in the chassis CAN messages that matter for LDW/FCW; trim differences are in comfort/body features.
- **Watch out:** 0x260 is `EMS16` (gas/cruise lamps) in the 2015_ccan layout, but newer comma code reuses 0x260 as `LKAS11` in the generated DBC — always decode by the DBC you're using **[verified live]**.

## Could not verify
- Exact broadcast rates for SAS11 (0x2B0), CGW1 (0x541), LVR11 (0x354), WHL_PUL11 (0x387), EMS15/EMS16 (0x547/0x260 on this layout), ABS11/ESP11 — not documented anywhere in opendbc; must be measured on the car.
- Whether every §B message is present with ignition on vs engine running — not documented; verify on the car.
- The 500 kbps figure is the well-established Hyundai C-CAN/ISO-15765 rate and comma default, but no Hyundai-published spec page was found for the LF Sonata; treat as "try 500k first, confirm frames decode."

## Sources
- DBC (primary): https://github.com/commaai/opendbc/blob/master/opendbc/dbc/hyundai_2015_ccan.dbc
- Generated DBC source: https://github.com/commaai/opendbc/blob/master/opendbc/dbc/generator/hyundai/hyundai_can.dbc
- carstate.py: https://github.com/commaai/opendbc/blob/master/opendbc/car/hyundai/carstate.py
- values.py (HYUNDAI_SONATA_LF): https://github.com/commaai/opendbc/blob/master/opendbc/car/hyundai/values.py
- fingerprints.py (HYUNDAI_SONATA_LF): https://github.com/commaai/opendbc/blob/master/opendbc/car/hyundai/fingerprints.py
- safety/modes/hyundai.h (RX rates): https://github.com/commaai/opendbc/blob/master/opendbc/safety/modes/hyundai.h
- CARS.md: https://github.com/commaai/opendbc/blob/master/docs/CARS.md
- docs_definitions.py (harnesses): https://github.com/commaai/opendbc/blob/master/opendbc/car/docs_definitions.py
