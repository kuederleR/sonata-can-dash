# Brake signal research — 2017 Sonata LF (no ADAS) OBD tap

## Observed on this car (dashboard msg ages)

| ID | Name | Status |
|---|---|---|
| 0x386 | WHL_SPD11 | present (ABS wheel speeds) |
| 0x2B0 | SAS11 | present |
| 0x316 | EMS11 | present (RPM) |
| 0x329 | EMS12 | present (throttle) |
| 0x260 | EMS16 | present |
| 0x111 / 0x112 | TCU11 / TCU12 | present (gear) |
| **0x394** | **TCS13** | **MISS** |
| 0x354 / 0x367 | LVR11 / LVR12 | MISS |

## Working decode on this OBD tap

TCS13 is still miss. Use EMS12 instead:

```text
EMS12 (0x329) BRAKE_ACT == 2   →  braking
EMS12 (0x329) BRAKE_ACT == 1   →  released
```

Verified with `probe_brake` (BRAKE_ACT histogram ~half 1 / half 2 while pumping the pedal).

### Candidates tried / considered

| Signal | Message | Notes |
|---|---|---|
| `DriverOverride` / `DriverBraking` / `BrakeLight` | TCS13 0x394 | Correct for openpilot; **absent here** |
| `BRAKE_ACT` | EMS12 0x329 bits 32\|2 | **Confirmed on car:** `1` = released, `2` = pressed. Earlier `> 0` decode latched forever because idle is already 1 |
| `BRAKE_ACT` | EMS_DCT12 0x81 bits 6\|2 | Alternate EMS→TCU field; presence unknown on this tap |
| `CF_Lvr_BkeAct` | LVR11 0x354 bit 5 | Brake-interlock for shifter; **LVR11 miss** |
| `CF_Tcu_BkeOnReq` | TCU13 0x113 | TCU brake-on request; presence unknown |
| `CF_Ems_BrkReq` / `CR_Ems_BstPre` | EMS19 0x492 | EMS brake request / booster pressure; presence unknown |
| `BLA_CTL` | TCS11 0x153 | Brake-lamp control from ESC; presence unknown |
| Park / fluid switches | CGW1/CGW2 | Not foot-pedal |

Note: ABS still publishes `WHL_SPD11`, so *some* chassis traffic reaches OBD — but the ESC status frame (`TCS13`) specifically does not. That matches a partial gateway / no-SCC bus view, not a dead CAN adapter.

## Next measurement

On the Jetson (ignition on, `can0` listen-only):

```bash
cd ~/sonata-can-dash && git pull
python -m can_reader.probe_brake --channel can0 --duration 25
```

Press and release the brake several times. Paste the report (especially any `← CHANGED` lines and the top bit-flip rows). Those identify the real decode target.

## References

- opendbc `hyundai_2015_ccan.dbc` — TCS13 / EMS12 layouts
- openpilot `carstate.py`: `ret.brakePressed = cp.vl["TCS13"]["DriverOverride"] == 2`
- openpilot issue #29921 — `DriverBraking` ≠ light pedal; use `DriverOverride`
