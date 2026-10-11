#!/usr/bin/env python3
"""One-time gear lever calibration for LVR11 (0x354) CF_Lvr_GearInf.

Enum values are NOT in the DBC. Run this with the car awake, shift through
P-R-N-D (and any others you care about), then save the mapping to gear_map.json.

Usage (on Jetson, live CAN):
  python -m can_reader.calibrate_gear
  python -m can_reader.calibrate_gear --channel can0

Usage (simulator — demos the UI; mapping will be synthetic):
  python -m can_reader.calibrate_gear --simulate
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from can_reader.decode import DEFAULT_GEAR_MAP, decode_message
from can_reader.signals import LVR11


def _observe_live(channel: str, interface: str, bitrate: int, duration: float) -> dict[int, int]:
    import can

    counts: dict[int, int] = {}
    bus = can.Bus(
        channel=channel,
        interface=interface,
        bitrate=bitrate,
        receive_own_messages=False,
    )
    print(f"Listening on {interface}:{channel} for {duration:.0f}s — shift P-R-N-D now.")
    print("(recv-only; never transmitting)\n")
    deadline = time.monotonic() + duration
    try:
        while time.monotonic() < deadline:
            msg = bus.recv(timeout=0.5)
            if msg is None or msg.arbitration_id != LVR11.can_id:
                continue
            decoded = decode_message(LVR11.can_id, bytes(msg.data))
            if not decoded:
                continue
            raw = int(decoded["CF_Lvr_GearInf"])
            counts[raw] = counts.get(raw, 0) + 1
            print(f"\r  CF_Lvr_GearInf = {raw}   (seen {counts[raw]}x)    ", end="", flush=True)
    finally:
        bus.shutdown()
    print()
    return counts


def _observe_sim(duration: float) -> dict[int, int]:
    from can_reader.simulator import Simulator

    sim = Simulator()
    counts: dict[int, int] = {}
    deadline = time.monotonic() + duration
    print(f"Simulator mode — collecting LVR11 for {duration:.0f}s…")
    while time.monotonic() < deadline:
        frame = sim.next_frame()
        if frame is None:
            time.sleep(0.005)
            continue
        can_id, data = frame
        if can_id != LVR11.can_id:
            continue
        decoded = decode_message(LVR11.can_id, data)
        if not decoded:
            continue
        raw = int(decoded["CF_Lvr_GearInf"])
        counts[raw] = counts.get(raw, 0) + 1
        print(f"\r  CF_Lvr_GearInf = {raw}   (seen {counts[raw]}x)    ", end="", flush=True)
        time.sleep(0.01)
    print()
    return counts


def _prompt_mapping(observed: dict[int, int]) -> dict[int, str]:
    print("\nObserved raw values (by count):")
    for raw, n in sorted(observed.items(), key=lambda x: -x[1]):
        print(f"  {raw}: {n} frames")

    labels = ["P", "R", "N", "D", "S", "M", "L", "B"]
    mapping: dict[int, str] = {}
    print("\nEnter the raw value for each gear (blank to skip):")
    for label in labels:
        raw_s = input(f"  {label} = ").strip()
        if not raw_s:
            continue
        try:
            raw = int(raw_s)
        except ValueError:
            print(f"  skip {label}: not an int")
            continue
        mapping[raw] = label
    return mapping


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calibrate LVR11 gear raw → label map")
    parser.add_argument("--simulate", action="store_true", help="Use synthetic frames")
    parser.add_argument("--channel", default="can0")
    parser.add_argument("--interface", default="socketcan")
    parser.add_argument("--bitrate", type=int, default=500_000)
    parser.add_argument("--duration", type=float, default=30.0, help="Observe seconds")
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_GEAR_MAP,
        help="Output JSON path (default: gear_map.json in repo root)",
    )
    args = parser.parse_args(argv)

    if args.simulate:
        observed = _observe_sim(args.duration)
    else:
        observed = _observe_live(args.channel, args.interface, args.bitrate, args.duration)

    if not observed:
        print("No LVR11 frames seen. Is the car awake / simulator running?", file=sys.stderr)
        return 1

    mapping = _prompt_mapping(observed)
    if not mapping:
        print("No mapping entered; nothing saved.")
        return 1

    args.out.write_text(json.dumps({str(k): v for k, v in sorted(mapping.items())}, indent=2) + "\n")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
