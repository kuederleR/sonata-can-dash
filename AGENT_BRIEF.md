# AGENT_BRIEF.md — Sonata CAN Dashboard (initial build)

You are building the initial project in this repo. **Read the research docs first** (`docs/RESEARCH-sonata-2017-lf.md`, then `docs/RESEARCH-jetson-obd-can.md`) — they contain the exact CAN signal table, Jetson CAN bring-up options, and wiring spec. Everything below assumes them.

## Mission

Build a system for a **2017 Hyundai Sonata Limited (LF, 2.4L, no ADAS)** that:
1. **Pulls comprehensive live data from the car** — a Python service on an **NVIDIA Jetson Orin Nano Super** passively sniffs the C-CAN broadcast (500 kbps, SocketCAN `can0`) via OBD-II pins 6/14 and decodes the opendbc `hyundai_2015_ccan` signal set.
2. **Serves a web dashboard the owner can view on his phone** — mobile-first, live-updating, reachable on the local network.
3. **Documents Jetson setup and wiring** so a competent builder can go from a bare Jetson to live car data.

## What to build

### 1. `can_reader/` — CAN acquisition + decode service
- Python, `python-can` on SocketCAN. Interface and bitrate configurable (defaults: `can0`, 500000). **Listen-only: never transmit CAN frames to the vehicle bus.**
- Decode layer driven by a data table of message ID → signals, using the exact IDs/bit positions/factors from `docs/RESEARCH-sonata-2017-lf.md` §B. Minimum signals: vehicle speed (0x4F1), wheel speeds FL/FR/RL/RR (0x386), steering angle + rate (0x2B0), brake light + driver-braking (0x394), turn signals L/R (0x541), gas pedal (0x260), gear lever (0x354), plus the bonus signals where cheap (longitudinal accel `aBasis`, standstill, parking brake, steering torque 0x251, odometer 0x5B0).
- Handle WHL_SPD11's alive-counter/checksum nibbles gracefully (validate, don't crash on mismatch). Handle the speed-unit flag (`CF_Clu_SPEED_UNIT`) and prefer WHL_SPD11 (always km/h).
- Gear enum values are NOT in the DBC — log raw values and provide a one-time calibration helper (script that prints observed LVR11 values while the user shifts P-R-N-D, then saves the mapping).
- **Simulator mode** (no car needed): generate synthetic frames / replay a candump log so the whole pipeline and dashboard run on any machine.
- Publish decoded state (e.g. in-process state object + JSON over a local socket or shared structure) for the dashboard to consume.

### 2. `dashboard/` — mobile-first web dashboard
- Lightweight Python web server (FastAPI or Flask) binding `0.0.0.0` on a documented port, serving a phone-friendly page with live updates (WebSocket or SSE).
- Displays: big vehicle speed readout, four wheel speeds, steering angle gauge/bar, steering rate, brake indicator (on/off), turn-signal indicators L/R, gear, throttle %, plus connection/health status (frames/sec, last-frame age, interface state).
- Works at phone viewport widths first; desktop is secondary. No build step / no npm if avoidable — plain HTML/CSS/JS served by the Python app.
- A single `run.py` / entrypoint that starts reader + dashboard together, with `--simulate` flag.

### 3. `docs/jetson-setup.md` — Jetson bring-up guide
Covered in the research doc; write it as step-by-step: JetPack version notes, enabling SocketCAN via **either** (a) SPI CAN adapter (MCP2515/MCP2518FD device-tree overlay on the 40-pin header) **or** (b) native J17/MTTCAN (solder J17 header, 3.3V transceiver, un-blacklist `mttcan`, manual pinmux for module pins 143/145), `can-utils` install, Python venv + `pip install -r requirements.txt`, verifying with `candump can0`, and a systemd service file for the reader.

### 4. `docs/wiring.md` — wiring guide
OBD-II pinout (4+5 GND, 6 CAN-H, 14 CAN-L, 16 +12V capped and insulated), transceiver wiring for both CAN options, **adapter termination OFF** (car provides ~60 Ω), polarity check, common ground, listen-only-first rule, car must be awake (RUN/engine on), multimeter continuity check on cheap pigtails.

### 5. `README.md` — project overview
What it is, architecture (ASCII diagram: car → OBD-II → CAN adapter → Jetson can_reader → dashboard → phone browser), quickstart (simulator mode first, then on-car), how to view the dashboard on a phone (Jetson on same Wi-Fi or phone hotspot; `http://<jetson-ip>:<port>`), and pointers to the docs.

## Constraints
- **Never transmit on the vehicle bus.** The reader opens the SocketCAN interface receive-only.
- Python 3.10+, type hints, `requirements.txt` pinned where it matters.
- Keep the decode table data-driven so adding signals is a table edit, not code surgery.
- Known gaps (do NOT try to fix now): yaw rate is not decoded on this car — leave a clearly-marked placeholder/stub for a future derived-yaw module; there is no radar — FCW vision work is out of scope for this build.
- The builder's exact CAN adapter model is unknown — keep the interface layer adapter-agnostic (any SocketCAN interface works).

## Acceptance criteria
- `python run.py --simulate` starts the reader in simulator mode and the dashboard shows live-updating values; the page is usable at 390px width.
- `docs/jetson-setup.md` + `docs/wiring.md` let a competent builder go from a bare Jetson Orin Nano Super to `candump` showing decoded Sonata frames.
- All commands documented; repo runs from its root with no hidden prerequisites beyond the docs.

## Build approach
Work autonomously. Read the research docs first, then build. Ask the user only if genuinely blocked.
