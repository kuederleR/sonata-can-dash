#!/usr/bin/env python3
"""Start CAN reader + mobile dashboard together.

Examples:
  python run.py --simulate
  python run.py --channel can0 --bitrate 500000
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure repo root is on sys.path when invoked as `python run.py`
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from can_reader.decode import FrameDecoder
from can_reader.reader import CanReader, FrameSourceReader
from can_reader.state import SharedState
from dashboard.app import create_app

log = logging.getLogger("sonata-can-dash")

DEFAULT_PORT = 8080


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sonata CAN Dashboard")
    p.add_argument(
        "--simulate",
        action="store_true",
        help="Generate synthetic CAN frames (no car / no SocketCAN needed)",
    )
    p.add_argument("--channel", default="can0", help="SocketCAN channel (default: can0)")
    p.add_argument(
        "--interface",
        default="socketcan",
        help="python-can interface name (default: socketcan)",
    )
    p.add_argument("--bitrate", type=int, default=500_000, help="CAN bitrate")
    p.add_argument("--host", default="0.0.0.0", help="Dashboard bind host")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help="Dashboard port")
    p.add_argument(
        "--gear-map",
        type=Path,
        default=ROOT / "gear_map.json",
        help="Path to gear_map.json from calibrate_gear",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    state = SharedState()
    decoder = FrameDecoder(state, gear_map_path=args.gear_map)

    if args.simulate:
        from can_reader.simulator import Simulator

        sim = Simulator()
        reader: CanReader | FrameSourceReader = FrameSourceReader(
            state,
            source=sim.next_frame,
            interface_label="simulator",
            decoder=decoder,
        )
        log.info("Starting in SIMULATOR mode (no vehicle bus)")
    else:
        reader = CanReader(
            state,
            channel=args.channel,
            interface=args.interface,
            bitrate=args.bitrate,
            decoder=decoder,
        )
        log.info(
            "Starting live reader on %s:%s @ %d (listen-only)",
            args.interface,
            args.channel,
            args.bitrate,
        )

    reader.start()
    app = create_app(state)

    import uvicorn

    log.info("Dashboard: http://%s:%d/  (phones: http://<this-host-ip>:%d/)", args.host, args.port, args.port)
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    finally:
        reader.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
