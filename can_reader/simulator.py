"""Synthetic CAN frame generator for offline / no-car testing."""

from __future__ import annotations

import math
import time
from collections import deque

from can_reader.checksum import apply_whl_spd11_checksum
from can_reader.decode import pack_signal
from can_reader.signals import (
    CGW1,
    CLU11,
    CLU12,
    EMS15,
    EMS16,
    LVR11,
    MDPS12,
    MESSAGES_BY_ID,
    SAS11,
    TCS13,
    WHL_SPD11,
)


def _empty_payload(dlc: int = 8) -> bytearray:
    return bytearray(dlc)


def _pack_msg(can_id: int, values: dict[str, float], dlc: int = 8) -> bytes:
    msg = MESSAGES_BY_ID[can_id]
    data = _empty_payload(dlc)
    specs = {s.name: s for s in msg.signals}
    for name, physical in values.items():
        pack_signal(data, specs[name], physical)
    if can_id == WHL_SPD11.can_id:
        apply_whl_spd11_checksum(data)
    return bytes(data)


class Simulator:
    """Generate a cycling set of Sonata-like frames and yield them on next_frame()."""

    def __init__(self) -> None:
        self._t0 = time.monotonic()
        self._alive = 0
        self._queue: deque[tuple[int, bytes]] = deque()
        self._last_emit = 0.0
        # Approximate rates (Hz)
        self._period = {
            WHL_SPD11.can_id: 0.01,   # 100 Hz
            TCS13.can_id: 0.01,
            CLU11.can_id: 0.02,       # 50 Hz
            SAS11.can_id: 0.02,
            EMS16.can_id: 0.01,
            EMS15.can_id: 0.05,
            CGW1.can_id: 0.05,
            LVR11.can_id: 0.1,
            MDPS12.can_id: 0.02,
            CLU12.can_id: 0.5,
        }
        self._next_due = {cid: 0.0 for cid in self._period}

    def next_frame(self) -> tuple[int, bytes] | None:
        now = time.monotonic()
        self._maybe_enqueue(now)
        if self._queue:
            return self._queue.popleft()
        return None

    def _maybe_enqueue(self, now: float) -> None:
        elapsed = now - self._t0
        # Synthetic "drive" profile
        speed = 40.0 + 25.0 * math.sin(elapsed * 0.15)  # km/h
        if speed < 0:
            speed = 0.0
        angle = 30.0 * math.sin(elapsed * 0.4)  # deg
        rate = abs(12.0 * math.cos(elapsed * 0.4))
        throttle = max(0.0, 35.0 + 25.0 * math.sin(elapsed * 0.2))
        braking = speed < 20.0 and math.sin(elapsed * 0.15) < -0.7
        blink_phase = int(elapsed * 2) % 2  # ~1 Hz blink
        turn_left = blink_phase and (int(elapsed / 8) % 3 == 1)
        turn_right = blink_phase and (int(elapsed / 8) % 3 == 2)
        gear_cycle = ["P", "R", "N", "D"]
        # Map to plausible raw values for demo (until calibrated)
        gear_raw_map = {"P": 1, "R": 2, "N": 3, "D": 4}
        gear_label = gear_cycle[min(3, int(elapsed / 12) % 4)] if speed < 5 else "D"
        gear_raw = gear_raw_map[gear_label]
        torque = 0.5 * math.sin(elapsed * 0.5)
        odo = 45231.0 + elapsed * 0.01

        for can_id, period in self._period.items():
            if now < self._next_due[can_id]:
                continue
            self._next_due[can_id] = now + period

            if can_id == WHL_SPD11.can_id:
                self._alive = (self._alive + 1) % 16
                # Pack speeds + alive counter; checksum applied in _pack_msg
                data = _empty_payload(8)
                for name, val in (
                    ("WHL_SPD_FL", speed),
                    ("WHL_SPD_FR", speed * 1.002),
                    ("WHL_SPD_RL", speed * 0.998),
                    ("WHL_SPD_RR", speed * 1.001),
                ):
                    spec = next(s for s in WHL_SPD11.signals if s.name == name)
                    pack_signal(data, spec, val)
                # Alive counter split LSB/MSB
                lsb_spec = next(
                    s for s in WHL_SPD11.signals if s.name == "WHL_SPD_AliveCounter_LSB"
                )
                msb_spec = next(
                    s for s in WHL_SPD11.signals if s.name == "WHL_SPD_AliveCounter_MSB"
                )
                pack_signal(data, lsb_spec, float(self._alive & 0x3))
                pack_signal(data, msb_spec, float((self._alive >> 2) & 0x3))
                apply_whl_spd11_checksum(data)
                self._queue.append((can_id, bytes(data)))

            elif can_id == CLU11.can_id:
                self._queue.append(
                    (
                        can_id,
                        _pack_msg(
                            can_id,
                            {
                                "CF_Clu_Vanz": speed,
                                "CF_Clu_SPEED_UNIT": 0.0,  # metric
                            },
                            dlc=4,
                        ),
                    )
                )

            elif can_id == SAS11.can_id:
                self._queue.append(
                    (
                        can_id,
                        _pack_msg(
                            can_id,
                            {"SAS_Angle": angle, "SAS_Speed": rate},
                            dlc=5,
                        ),
                    )
                )

            elif can_id == TCS13.can_id:
                self._queue.append(
                    (
                        can_id,
                        _pack_msg(
                            can_id,
                            {
                                "aBasis": (0.0 if abs(speed) < 1 else 0.3),
                                "BrakeLight": 1.0 if braking else 0.0,
                                "DriverOverride": 2.0 if braking else 0.0,
                                "StandStill": 1.0 if speed < 0.5 else 0.0,
                                "PBRAKE_ACT": 1.0 if gear_label == "P" else 0.0,
                                "DriverBraking": 1.0 if braking else 0.0,
                            },
                        ),
                    )
                )

            elif can_id == CGW1.can_id:
                self._queue.append(
                    (
                        can_id,
                        _pack_msg(
                            can_id,
                            {
                                "CF_Gway_TurnSigLh": 1.0 if turn_left else 0.0,
                                "CF_Gway_TurnSigRh": 1.0 if turn_right else 0.0,
                            },
                        ),
                    )
                )

            elif can_id == EMS16.can_id:
                self._queue.append(
                    (
                        can_id,
                        _pack_msg(
                            can_id,
                            {"CF_Ems_AclAct": 1.0 if throttle > 5 and not braking else 0.0},
                        ),
                    )
                )

            elif can_id == EMS15.can_id:
                self._queue.append(
                    (
                        can_id,
                        _pack_msg(can_id, {"FA_PV_CAN": 0.0 if braking else throttle}),
                    )
                )

            elif can_id == LVR11.can_id:
                self._queue.append(
                    (
                        can_id,
                        _pack_msg(can_id, {"CF_Lvr_GearInf": float(gear_raw)}, dlc=7),
                    )
                )

            elif can_id == MDPS12.can_id:
                self._queue.append(
                    (can_id, _pack_msg(can_id, {"CR_Mdps_StrColTq": torque}))
                )

            elif can_id == CLU12.can_id:
                self._queue.append(
                    (
                        can_id,
                        _pack_msg(can_id, {"CF_Clu_Odometer": odo}, dlc=4),
                    )
                )

