"""Little-endian CAN signal extract + frame → VehicleState updates."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from can_reader.checksum import validate_whl_spd11
from can_reader.signals import MESSAGES_BY_ID, SignalSpec, WHL_SPD11
from can_reader.state import SharedState
from can_reader.yaw_stub import yaw_rate_deg_s

log = logging.getLogger(__name__)

# Default location for gear calibration output (repo root when run via run.py)
DEFAULT_GEAR_MAP = Path(__file__).resolve().parent.parent / "gear_map.json"

# openpilot hyundai_can.dbc VAL_ tables (Sonata LF uses TCU_GEARS → CUR_GR)
CUR_GR_MAP: dict[int, str] = {
    0: "P",
    1: "D",
    2: "D",
    3: "D",
    4: "D",
    5: "D",
    6: "D",
    7: "D",
    8: "D",
    14: "R",
}

# LVR12 CF_Lvr_Gear VAL_ (and often matches G_SEL_DISP)
LVR12_GEAR_MAP: dict[int, str] = {
    0: "P",
    5: "D",
    6: "N",
    7: "R",
    8: "S",
    12: "T",
}


def extract_bits(data: bytes, start_bit: int, length: int, signed: bool = False) -> int:
    """Extract an Intel (little-endian) bitfield from a CAN payload."""
    raw = 0
    for i in range(length):
        bit = start_bit + i
        byte_i = bit // 8
        bit_i = bit % 8
        if byte_i >= len(data):
            break
        if (data[byte_i] >> bit_i) & 1:
            raw |= 1 << i
    if signed and length > 0 and (raw & (1 << (length - 1))):
        raw -= 1 << length
    return raw


def decode_signal(data: bytes, spec: SignalSpec) -> float:
    raw = extract_bits(data, spec.start_bit, spec.length, signed=spec.signed)
    return raw * spec.factor + spec.offset


def decode_message(can_id: int, data: bytes) -> dict[str, float] | None:
    msg = MESSAGES_BY_ID.get(can_id)
    if msg is None:
        return None
    return {s.name: decode_signal(data, s) for s in msg.signals}


def pack_signal(data: bytearray, spec: SignalSpec, physical: float) -> None:
    """Pack a physical value into an Intel bitfield (simulator use)."""
    if spec.factor == 0:
        raw = 0
    else:
        raw = int(round((physical - spec.offset) / spec.factor))
    if spec.signed:
        max_pos = (1 << (spec.length - 1)) - 1
        min_neg = -(1 << (spec.length - 1))
        raw = max(min_neg, min(max_pos, raw))
        if raw < 0:
            raw += 1 << spec.length
    else:
        raw = max(0, min((1 << spec.length) - 1, raw))
    for i in range(spec.length):
        bit = spec.start_bit + i
        byte_i = bit // 8
        bit_i = bit % 8
        while len(data) <= byte_i:
            data.append(0)
        if (raw >> i) & 1:
            data[byte_i] |= 1 << bit_i
        else:
            data[byte_i] &= ~(1 << bit_i)


def load_gear_map(path: Path | None = None) -> dict[int, str]:
    path = path or DEFAULT_GEAR_MAP
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text())
        out: dict[int, str] = {}
        for k, v in raw.items():
            if isinstance(k, str) and not k.lstrip("-").isdigit():
                continue  # skip _comment / metadata keys
            out[int(k)] = str(v)
        return out
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        log.warning("Failed to load gear map %s: %s", path, exc)
        return {}


class FrameDecoder:
    """Apply decoded signals onto SharedState."""

    def __init__(
        self,
        state: SharedState,
        gear_map: dict[int, str] | None = None,
        gear_map_path: Path | None = None,
    ) -> None:
        self.state = state
        # User calibration overrides built-in maps when present
        self.gear_map = gear_map if gear_map is not None else load_gear_map(gear_map_path)

    def handle_frame(self, can_id: int, data: bytes) -> None:
        checksum_error = False
        if can_id == WHL_SPD11.can_id:
            if not validate_whl_spd11(data):
                checksum_error = True
                log.debug("WHL_SPD11 checksum mismatch (continuing decode)")

        decoded = decode_message(can_id, data)
        self.state.note_frame(can_id=can_id, checksum_error=checksum_error)
        if decoded is None:
            return

        updates = self._to_vehicle_updates(can_id, decoded)
        updates["yaw_rate_deg_s"] = yaw_rate_deg_s()
        if updates:
            self.state.update_vehicle(**updates)

    # Prefer cluster/lever PRNDL over TCU CUR_GR (which collapses D1–D8 to "D")
    _GEAR_PRIORITY = {"TCU11": 3, "LVR12": 3, "TCU12": 2, "LVR11": 1}

    def _map_gear(self, raw: int, builtin: dict[int, str], source: str) -> dict[str, Any]:
        current_src = self.state.gear_source()
        cur_pri = self._GEAR_PRIORITY.get(current_src or "", 0)
        new_pri = self._GEAR_PRIORITY.get(source, 0)
        if new_pri < cur_pri:
            return {}
        label = self.gear_map.get(raw)
        if label is None:
            label = builtin.get(raw)
        if label is None:
            label = f"RAW:{raw}"
        return {"gear_raw": raw, "gear": label, "gear_source": source}

    def _to_vehicle_updates(self, can_id: int, d: dict[str, float]) -> dict[str, Any]:
        if can_id == 0x4F1:  # CLU11
            unit_metric = int(d["CF_Clu_SPEED_UNIT"]) == 0
            vanz = d["CF_Clu_Vanz"]
            cluster_kmh = vanz if unit_metric else vanz * 1.60934
            return {
                "speed_unit_metric": unit_metric,
                "cluster_speed_kmh": cluster_kmh,
            }

        if can_id == 0x386:  # WHL_SPD11
            fl, fr, rl, rr = (
                d["WHL_SPD_FL"],
                d["WHL_SPD_FR"],
                d["WHL_SPD_RL"],
                d["WHL_SPD_RR"],
            )
            return {
                "wheel_fl_kmh": fl,
                "wheel_fr_kmh": fr,
                "wheel_rl_kmh": rl,
                "wheel_rr_kmh": rr,
                "speed_kmh": (fl + fr + rl + rr) / 4.0,
            }

        if can_id == 0x2B0:  # SAS11
            return {
                "steering_angle_deg": d["SAS_Angle"],
                "steering_rate_deg_s": d["SAS_Speed"],
            }

        if can_id == 0x394:  # TCS13 — openpilot brakePressed = DriverOverride == 2
            override = int(d["DriverOverride"])
            return {
                "accel_long_mps2": d["aBasis"],
                "brake_light": bool(int(d["BrakeLight"])),
                "driver_braking": override == 2,
                "brake_source": "TCS13",
                "standstill": bool(int(d["StandStill"])),
                "parking_brake": bool(int(d["PBRAKE_ACT"])),
            }

        if can_id == 0x541:  # CGW1
            return {
                "turn_left": int(d["CF_Gway_TurnSigLh"]) > 0,
                "turn_right": int(d["CF_Gway_TurnSigRh"]) > 0,
            }

        if can_id == 0x316:  # EMS11 — engine RPM
            return {"rpm": d["N"]}

        if can_id == 0x329:  # EMS12 — pedal; brake fallback when TCS13 absent
            updates: dict[str, Any] = {
                "throttle_pct": d["PV_AV_CAN"],
                "gas_pressed": d["PV_AV_CAN"] > 1.0,
            }
            # This car's OBD bus has no TCS13 — use BRAKE_ACT, always assign
            # both True and False so the indicator cannot latch.
            tcs_age = self.state.msg_age_s(0x394)
            if tcs_age is None or tcs_age > 0.5:
                updates["driver_braking"] = int(d["BRAKE_ACT"]) > 0
                updates["brake_source"] = "EMS12"
            return updates

        if can_id == 0x260:  # EMS16
            return {"gas_pressed": int(d["CF_Ems_AclAct"]) > 0}

        if can_id == 0x547:  # EMS15 alternate pedal
            return {"throttle_pct": d["FA_PV_CAN"], "gas_pressed": d["FA_PV_CAN"] > 1.0}

        if can_id == 0x112:  # TCU12 CUR_GR (Sonata LF TCU_GEARS)
            return self._map_gear(int(d["CUR_GR"]), CUR_GR_MAP, "TCU12")

        if can_id == 0x111:  # TCU11 G_SEL_DISP — cluster gear display
            # Prefer LVR12-style PRNDL mapping; falls back to RAW
            return self._map_gear(int(d["G_SEL_DISP"]), LVR12_GEAR_MAP, "TCU11")

        if can_id == 0x367:  # LVR12
            return self._map_gear(int(d["CF_Lvr_Gear"]), LVR12_GEAR_MAP, "LVR12")

        if can_id == 0x354:  # LVR11 — last-resort / calibration helper
            return self._map_gear(int(d["CF_Lvr_GearInf"]), {}, "LVR11")

        if can_id == 0x251:  # MDPS12
            return {"steering_torque_nm": d["CR_Mdps_StrColTq"]}

        if can_id == 0x5B0:  # CLU12
            return {"odometer_km": d["CF_Clu_Odometer"]}

        return {}
