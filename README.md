# Sonata CAN Dashboard

Live vehicle data for a **2017 Hyundai Sonata Limited (LF, 2.4L, no ADAS)** on an **NVIDIA Jetson Orin Nano Super**.

A Python service passively sniffs the C-CAN broadcast (500 kbps, SocketCAN) via OBD-II pins 6/14, decodes the opendbc `hyundai_2015_ccan` signal set, and serves a mobile-first web dashboard on the local network.

## Architecture

```text
  ┌─────────┐   OBD-II 6/14    ┌──────────────┐   SocketCAN    ┌────────────┐
  │  Sonata │ ───────────────► │ CAN adapter  │ ─────────────► │   Jetson   │
  │  C-CAN  │   500 kbps RX    │ (SPI or J17) │    can0 RX     │            │
  └─────────┘                  └──────────────┘                │ can_reader │
                                                                │     │      │
                                                                │     ▼      │
                                                                │ dashboard  │
                                                                │  :8080     │
                                                                └─────┬──────┘
                                                                      │ Wi-Fi
                                                                      ▼
                                                               ┌────────────┐
                                                               │   Phone    │
                                                               │  browser   │
                                                               └────────────┘
```

**Listen-only:** the reader never transmits CAN frames to the vehicle bus.

## Quickstart (simulator — no car needed)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py --simulate
```

Open **http://127.0.0.1:8080** (or `http://<host-ip>:8080` from your phone on the same network). Values update live; the layout targets ~390px phone width.

## On-car

1. Wire OBD-II per [docs/wiring.md](docs/wiring.md).
2. Bring up SocketCAN per [docs/jetson-setup.md](docs/jetson-setup.md) (`listen-only on`, 500000).
3. Confirm traffic: `candump can0`
4. Run:

```bash
python run.py --channel can0 --bitrate 500000
```

5. On your phone (same Wi-Fi as the Jetson, or phone hotspot): **http://\<jetson-ip\>:8080**

Built-in gear maps cover Sonata LF (`TCU11`/`TCU12`). Optional override if labels are wrong:

```bash
python -m can_reader.calibrate_gear --channel can0
```

Writes `gear_map.json` in the repo root. The dashboard **CAN IDs (age)** strip shows which IDs are present (`TCS13` is miss on this car’s OBD tap).

Brake: TCS13 is miss on this OBD tap; dashboard uses **EMS12 `BRAKE_ACT == 2`** (1 = released). Re-probe if needed:

```bash
python -m can_reader.probe_brake --channel can0 --duration 25
```

See [docs/RESEARCH-brake-signal.md](docs/RESEARCH-brake-signal.md).

## What the dashboard shows

- Vehicle speed (mean of wheel speeds, km/h)
- Four wheel speeds, steering angle + rate
- Brake indicator, turn signals L/R, gear, throttle %
- Health: interface name, frames/sec, last-frame age, checksum error count

## Layout

| Path | Role |
|---|---|
| `can_reader/` | SocketCAN listen-only reader, data-driven decode table, simulator, gear calibrator |
| `dashboard/` | FastAPI + plain HTML/CSS/JS (WebSocket live updates) |
| `run.py` | Starts reader + dashboard together |
| `docs/jetson-setup.md` | JetPack, SPI vs J17/MTTCAN, systemd |
| `docs/wiring.md` | OBD pins, termination, polarity |
| `docs/RESEARCH-*.md` | Signal table and Jetson research this build is based on |

## Known gaps (out of scope)

- **Yaw rate** — not in `hyundai_2015_ccan` for this car; see `can_reader/yaw_stub.py` for a future derived-yaw / IMU hook.
- **Radar / FCW vision** — this car has no SCC radar; not part of this build.

## License / provenance

Signal layouts come from comma.ai [opendbc](https://github.com/commaai/opendbc) `hyundai_2015_ccan.dbc`, validated against a 2017 LF Sonata. See the research docs for citations.
