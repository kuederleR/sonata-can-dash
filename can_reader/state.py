"""Thread-safe shared vehicle state published to the dashboard."""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class VehicleState:
    """Decoded vehicle signals. Units are SI-ish / dashboard-friendly."""

    # Primary speed (mean of wheel speeds, always km/h)
    speed_kmh: float | None = None
    # Cluster speed converted to km/h when unit flag is known
    cluster_speed_kmh: float | None = None
    speed_unit_metric: bool | None = None

    wheel_fl_kmh: float | None = None
    wheel_fr_kmh: float | None = None
    wheel_rl_kmh: float | None = None
    wheel_rr_kmh: float | None = None

    steering_angle_deg: float | None = None
    steering_rate_deg_s: float | None = None
    steering_torque_nm: float | None = None

    brake_light: bool | None = None
    driver_braking: bool | None = None
    brake_source: str | None = None  # TCS13 | EMS12
    standstill: bool | None = None
    parking_brake: bool | None = None
    accel_long_mps2: float | None = None

    turn_left: bool | None = None
    turn_right: bool | None = None

    gas_pressed: bool | None = None
    throttle_pct: float | None = None
    rpm: float | None = None

    gear_raw: int | None = None
    gear: str | None = None  # mapped label if gear_map.json present
    gear_source: str | None = None  # which message produced gear

    odometer_km: float | None = None

    # Placeholder — yaw is not decoded on this car (see yaw_stub.py)
    yaw_rate_deg_s: float | None = None


@dataclass
class Health:
    connected: bool = False
    interface: str = "unknown"
    frames_per_sec: float = 0.0
    last_frame_age_s: float | None = None
    checksum_errors: int = 0
    total_frames: int = 0
    last_frame_monotonic: float | None = None
    # can_id hex -> seconds since last seen (filled in snapshot)
    msg_age_s: dict[str, float | None] = field(default_factory=dict)


@dataclass
class SharedState:
    """Mutable state shared between reader thread and dashboard."""

    vehicle: VehicleState = field(default_factory=VehicleState)
    health: Health = field(default_factory=Health)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _msg_last: dict[int, float] = field(default_factory=dict, repr=False)

    def update_vehicle(self, **kwargs: Any) -> None:
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self.vehicle, key):
                    setattr(self.vehicle, key, value)

    def gear_source(self) -> str | None:
        with self._lock:
            return self.vehicle.gear_source

    def msg_age_s(self, can_id: int) -> float | None:
        with self._lock:
            t = self._msg_last.get(can_id)
            if t is None:
                return None
            return time.monotonic() - t

    def note_frame(self, can_id: int | None = None, checksum_error: bool = False) -> None:
        with self._lock:
            now = time.monotonic()
            self.health.total_frames += 1
            self.health.last_frame_monotonic = now
            self.health.connected = True
            if can_id is not None:
                self._msg_last[can_id] = now
            if checksum_error:
                self.health.checksum_errors += 1

    def set_health(self, **kwargs: Any) -> None:
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self.health, key):
                    setattr(self.health, key, value)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            now = time.monotonic()
            age: float | None = None
            if self.health.last_frame_monotonic is not None:
                age = now - self.health.last_frame_monotonic
            health = asdict(self.health)
            health["last_frame_age_s"] = age
            health.pop("last_frame_monotonic", None)
            # Per-message ages for watched IDs (set by decoder via note_frame)
            from can_reader.signals import WATCHED_IDS

            msg_age: dict[str, float | None] = {}
            for cid, name in WATCHED_IDS.items():
                t = self._msg_last.get(cid)
                msg_age[name] = None if t is None else round(now - t, 3)
            health["msg_age_s"] = msg_age
            return {
                "vehicle": asdict(self.vehicle),
                "health": health,
                "ts": time.time(),
            }
