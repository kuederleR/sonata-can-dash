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
        return {int(k): str(v) for k, v in raw.items()}
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
        self.gear_map = gear_map if gear_map is not None else load_gear_map(gear_map_path)

    def handle_frame(self, can_id: int, data: bytes) -> None:
        checksum_error = False
        if can_id == WHL_SPD11.can_id:
            if not validate_whl_spd11(data):
                checksum_error = True
                log.debug("WHL_SPD11 checksum mismatch (continuing decode)")

        decoded = decode_message(can_id, data)
        self.state.note_frame(checksum_error=checksum_error)
        if decoded is None:
            return

        updates = self._to_vehicle_updates(can_id, decoded)
        # Always stamp yaw stub so the field stays explicit
        updates["yaw_rate_deg_s"] = yaw_rate_deg_s()
        if updates:
            self.state.update_vehicle(**updates)

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

        if can_id == 0x394:  # TCS13
            override = int(d["DriverOverride"])
            return {
                "accel_long_mps2": d["aBasis"],
                "brake_light": bool(int(d["BrakeLight"])),
                "driver_braking": bool(int(d["DriverBraking"])) or override == 2,
                "standstill": bool(int(d["StandStill"])),
                "parking_brake": bool(int(d["PBRAKE_ACT"])),
            }

        if can_id == 0x541:  # CGW1
            return {
                "turn_left": int(d["CF_Gway_TurnSigLh"]) > 0,
                "turn_right": int(d["CF_Gway_TurnSigRh"]) > 0,
            }

        if can_id == 0x260:  # EMS16
            return {"gas_pressed": int(d["CF_Ems_AclAct"]) > 0}

        if can_id == 0x547:  # EMS15
            return {"throttle_pct": d["FA_PV_CAN"]}

        if can_id == 0x354:  # LVR11
            raw = int(d["CF_Lvr_GearInf"])
            label = self.gear_map.get(raw)
            return {
                "gear_raw": raw,
                "gear": label if label is not None else f"RAW:{raw}",
            }

        if can_id == 0x251:  # MDPS12
            return {"steering_torque_nm": d["CR_Mdps_StrColTq"]}

        if can_id == 0x5B0:  # CLU12
            return {"odometer_km": d["CF_Clu_Odometer"]}

        return {}
