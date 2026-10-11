#!/usr/bin/env python3
"""One-time gear calibration — watches TCU11 / TCU12 / LVR11 / LVR12.

Sonata LF is TCU_GEARS in openpilot: prefer TCU12 CUR_GR or TCU11 G_SEL_DISP.
LVR11 is a last-resort fallback.

Usage:
  python -m can_reader.calibrate_gear --channel can0
  python -m can_reader.calibrate_gear --simulate
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

from can_reader.decode import DEFAULT_GEAR_MAP, decode_message

WATCH = {
    0x111: ("TCU11", "G_SEL_DISP"),
    0x112: ("TCU12", "CUR_GR"),
    0x354: ("LVR11", "CF_Lvr_GearInf"),
    0x367: ("LVR12", "CF_Lvr_Gear"),
}


def _observe_live(channel: str, interface: str, bitrate: int, duration: float) -> dict[str, dict[int, int]]:
    import can

    counts: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
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
            if msg is None or msg.arbitration_id not in WATCH:
                continue
            name, sig = WATCH[msg.arbitration_id]
            decoded = decode_message(msg.arbitration_id, bytes(msg.data))
            if not decoded or sig not in decoded:
                continue
            raw = int(decoded[sig])
            counts[name][raw] += 1
            print(f"\r  {name}.{sig} = {raw}   (seen {counts[name][raw]}x)    ", end="", flush=True)
    finally:
        bus.shutdown()
    print()
    return {k: dict(v) for k, v in counts.items()}


def _observe_sim(duration: float) -> dict[str, dict[int, int]]:
    from can_reader.simulator import Simulator

    sim = Simulator()
    counts: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    deadline = time.monotonic() + duration
    print(f"Simulator mode — collecting gear msgs for {duration:.0f}s…")
    while time.monotonic() < deadline:
        frame = sim.next_frame()
        if frame is None:
            time.sleep(0.005)
            continue
        can_id, data = frame
        if can_id not in WATCH:
            continue
        name, sig = WATCH[can_id]
        decoded = decode_message(can_id, data)
        if not decoded or sig not in decoded:
            continue
        raw = int(decoded[sig])
        counts[name][raw] += 1
        print(f"\r  {name}.{sig} = {raw}   (seen {counts[name][raw]}x)    ", end="", flush=True)
        time.sleep(0.01)
    print()
    return {k: dict(v) for k, v in counts.items()}


def _prompt_mapping(observed: dict[str, dict[int, int]]) -> dict[int, str]:
    print("\nObserved raw values by message:")
    for name, vals in sorted(observed.items()):
        print(f"  {name}:")
        for raw, n in sorted(vals.items(), key=lambda x: -x[1]):
            print(f"    {raw}: {n} frames")

    print(
        "\nEnter raw values for the message you want to use "
        "(built-in TCU12/TCU11/LVR12 maps often work without this)."
    )
    labels = ["P", "R", "N", "D", "S", "M", "L", "B"]
    mapping: dict[int, str] = {}
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
    parser = argparse.ArgumentParser(description="Calibrate gear raw → label map")
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
        print(
            "No gear frames seen (TCU11/TCU12/LVR11/LVR12). "
            "Is the car awake / bus connected?",
            file=sys.stderr,
        )
        return 1

    mapping = _prompt_mapping(observed)
    if not mapping:
        print("No mapping entered; nothing saved. Built-in maps still apply.")
        return 0

    args.out.write_text(
        json.dumps({str(k): v for k, v in sorted(mapping.items())}, indent=2) + "\n"
    )
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
