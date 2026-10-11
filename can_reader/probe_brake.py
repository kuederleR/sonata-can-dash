#!/usr/bin/env python3
"""Passive brake-signal probe for Sonata LF OBD taps missing TCS13.

openpilot's brakePressed comes from TCS13.DriverOverride==2. This car's OBD
bus has TCS13 miss, and EMS12.BRAKE_ACT does not track the pedal on at least
one 2017 LF. This tool finds which IDs/bits actually flip when you press brake.

Usage (on Jetson, ignition on, listen-only can0):
  python -m can_reader.probe_brake --channel can0 --duration 25

Press and release the brake several times during the run. At the end it prints:
  1) named candidate signal value histograms
  2) bit-level flips on every ID that changed (best leads for a new decode)

Never transmits.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field

from can_reader.decode import extract_bits
from can_reader.signals import SignalSpec

# Named DBC candidates that *might* carry brake / stop-lamp / BKE status.
CANDIDATES: dict[int, tuple[str, tuple[SignalSpec, ...]]] = {
    0x329: (
        "EMS12",
        (
            SignalSpec("BRAKE_ACT", 32, 2),
            SignalSpec("PV_AV_CAN", 48, 8, factor=0.3906),
            SignalSpec("ACC_ACT", 30, 1),
        ),
    ),
    0x81: (
        "EMS_DCT12",
        (SignalSpec("BRAKE_ACT", 6, 2),),
    ),
    0x394: (
        "TCS13",
        (
            SignalSpec("BrakeLight", 11, 1),
            SignalSpec("DriverOverride", 45, 2),
            SignalSpec("DriverBraking", 55, 1),
            SignalSpec("PBRAKE_ACT", 53, 1),
        ),
    ),
    0x153: (
        "TCS11",
        (
            SignalSpec("ABS_ACT", 10, 1),
            SignalSpec("CF_Esc_BrkCtl", 48, 1),
            SignalSpec("BLA_CTL", 49, 2),
        ),
    ),
    0x38A: (
        "ABS11",
        (
            SignalSpec("ABS_ACT", 2, 1),
            SignalSpec("ESS_STAT", 6, 2),
        ),
    ),
    0x354: (
        "LVR11",
        (SignalSpec("CF_Lvr_BkeAct", 5, 1),),
    ),
    0x113: (
        "TCU13",
        (SignalSpec("CF_Tcu_BkeOnReq", 16, 2),),
    ),
    0x492: (
        "EMS19",
        (
            SignalSpec("CF_Ems_BrkReq", 0, 1),
            SignalSpec("CR_Ems_BstPre", 20, 12, factor=1.322),
        ),
    ),
    0x541: (
        "CGW1",
        (SignalSpec("CF_Gway_ParkBrakeSw", 60, 2),),
    ),
    0x553: (
        "CGW2",
        (SignalSpec("CF_Gway_BrakeFluidSw", 17, 1),),
    ),
}


@dataclass
class IdStats:
    name: str
    frames: int = 0
    last: bytes | None = None
    # bit_index -> set of values observed (0/1)
    bit_values: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    # bit_index -> flip count
    bit_flips: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    # named signal -> value -> count
    signal_hist: dict[str, dict[float, int]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(int))
    )


def _decode_candidates(can_id: int, data: bytes, stats: IdStats) -> None:
    entry = CANDIDATES.get(can_id)
    if entry is None:
        return
    _, specs = entry
    for spec in specs:
        raw = extract_bits(data, spec.start_bit, spec.length, signed=spec.signed)
        phys = raw * spec.factor + spec.offset
        # Round lightly so float histograms collapse
        key = round(phys, 3) if spec.factor != 1.0 else float(raw)
        stats.signal_hist[spec.name][key] += 1


def _observe_live(
    channel: str, interface: str, bitrate: int, duration: float
) -> dict[int, IdStats]:
    import can

    stats: dict[int, IdStats] = {}
    bus = can.Bus(
        channel=channel,
        interface=interface,
        bitrate=bitrate,
        receive_own_messages=False,
    )
    print(f"Listening on {interface}:{channel} for {duration:.0f}s (recv-only).")
    print("Press and release the BRAKE pedal several times now.\n")
    deadline = time.monotonic() + duration
    last_print = 0.0
    try:
        while time.monotonic() < deadline:
            msg = bus.recv(timeout=0.2)
            if msg is None:
                continue
            can_id = msg.arbitration_id
            data = bytes(msg.data)
            if can_id not in stats:
                name = CANDIDATES[can_id][0] if can_id in CANDIDATES else f"0x{can_id:03X}"
                stats[can_id] = IdStats(name=name)
            st = stats[can_id]
            st.frames += 1
            if st.last is not None:
                # XOR up to max length
                n = max(len(st.last), len(data))
                a = st.last.ljust(n, b"\x00")
                b = data.ljust(n, b"\x00")
                for bi in range(n * 8):
                    byte_i, bit_i = divmod(bi, 8)
                    prev = (a[byte_i] >> bit_i) & 1
                    cur = (b[byte_i] >> bit_i) & 1
                    st.bit_values[bi].add(cur)
                    if prev != cur:
                        st.bit_flips[bi] += 1
            else:
                for bi in range(len(data) * 8):
                    byte_i, bit_i = divmod(bi, 8)
                    st.bit_values[bi].add((data[byte_i] >> bit_i) & 1)
            st.last = data
            _decode_candidates(can_id, data, st)

            now = time.monotonic()
            if now - last_print > 1.0:
                last_print = now
                left = max(0.0, deadline - now)
                # Live EMS12 BRAKE_ACT if present
                ems = stats.get(0x329)
                ba = None
                if ems and ems.last and len(ems.last) > 4:
                    ba = extract_bits(ems.last, 32, 2)
                print(
                    f"  …{left:4.0f}s left | IDs seen={len(stats)} | "
                    f"EMS12.BRAKE_ACT={ba}",
                    flush=True,
                )
    finally:
        bus.shutdown()
    return stats


def _report(stats: dict[int, IdStats]) -> int:
    if not stats:
        print("No frames seen. Is can0 up / ignition on?", file=sys.stderr)
        return 1

    print("\n=== Named candidate signals (value → frame count) ===")
    any_named = False
    for can_id in sorted(CANDIDATES):
        st = stats.get(can_id)
        label = CANDIDATES[can_id][0]
        if st is None:
            print(f"  {label} 0x{can_id:03X}: MISS")
            continue
        any_named = True
        print(f"  {label} 0x{can_id:03X}: {st.frames} frames")
        for sig, hist in sorted(st.signal_hist.items()):
            top = sorted(hist.items(), key=lambda x: -x[1])[:8]
            parts = ", ".join(f"{v}×{n}" for v, n in top)
            varied = len(hist) > 1
            flag = "  ← CHANGED" if varied else ""
            print(f"    {sig}: {parts}{flag}")

    print("\n=== Bit flips (IDs that changed; ignore high-rate counters) ===")
    print("Bits that took both 0 and 1 are the best pedal candidates.\n")
    scored: list[tuple[int, int, int, str]] = []
    for can_id, st in stats.items():
        for bit, flips in st.bit_flips.items():
            vals = st.bit_values.get(bit, set())
            if vals == {0, 1} and flips >= 2:
                scored.append((flips, can_id, bit, st.name))
    scored.sort(reverse=True)
    if not scored:
        print("  No stable 0/1 bit flips found. Try a longer --duration and firm presses.")
    else:
        for flips, can_id, bit, name in scored[:40]:
            byte_i, bit_i = divmod(bit, 8)
            print(
                f"  {name:12} 0x{can_id:03X}  bit {bit:2d} "
                f"(byte{byte_i} bit{bit_i})  flips={flips}"
            )

    print("\n=== Presence summary ===")
    for can_id, (name, _) in CANDIDATES.items():
        st = stats.get(can_id)
        print(f"  {name:12} 0x{can_id:03X}  {'OK '+str(st.frames)+' fr' if st else 'MISS'}")

    if not any_named:
        print(
            "\nNo named brake candidates were on the bus. Paste this whole report "
            "back and we can wire whatever bit-flip line correlated with the pedal.",
            file=sys.stderr,
        )
    else:
        print(
            "\nPaste the CHANGED signal lines + top bit-flip rows back into chat "
            "to wire the dashboard."
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Probe CAN for brake pedal signal")
    p.add_argument("--channel", default="can0")
    p.add_argument("--interface", default="socketcan")
    p.add_argument("--bitrate", type=int, default=500_000)
    p.add_argument("--duration", type=float, default=25.0)
    args = p.parse_args(argv)
    stats = _observe_live(args.channel, args.interface, args.bitrate, args.duration)
    return _report(stats)


if __name__ == "__main__":
    raise SystemExit(main())
