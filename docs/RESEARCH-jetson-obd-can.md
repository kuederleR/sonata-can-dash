# CAN Bus → NVIDIA Jetson Orin Nano Super: Decoded Vehicle Data for DIY LDW/FCW

**Mission date:** 2026-10-01. **Goal:** Pull decoded vehicle data off the OBD-II port / CAN bus into a Jetson Orin Nano Super for a DIY camera-based lane departure warning (LDW) + forward collision warning (FCW) system. Builder has a CAN bus adapter for the Jetson and will solder an OBD-II connector onto it.

## Summary

- **Two data paths exist, and only one works for real-time LDW/FCW.** Standard OBD-II diagnostic polling (SAE J1979) yields ~1–10 Hz per PID with 10s–100s of ms latency per request — fine for dashboards, far too slow for a 10–30 Hz warning loop. Passive sniffing of the car's broadcast CAN frames (500 kbps) gives wheel speeds, steering angle, yaw rate, brake state at 10–100 Hz with near-zero added latency — this is the path the build should use.
- **J1979 standard PIDs do NOT include the signals LDW/FCW need most** (steering angle, yaw rate, individual wheel speeds, brake pedal, turn signals). You get vehicle speed, RPM, throttle, coolant etc. from J1979 — the rest must come from manufacturer-proprietary broadcast frames, decoded with a per-vehicle DBC file.
- **comma.ai's opendbc is the single most important resource**: 397 supported cars (as of April 2026), DBC files in `opendbc/dbc/`, decode with `cantools` or opendbc's own `CANParser`. Always check the builder's exact make/model/year against opendbc coverage.
- **Correction to a common assumption: the Orin Nano's T234 SoC DOES have a native CAN controller** (MTTCAN, CAN FD up to 5 Mbps, SocketCAN via the `mttcan` driver). What the dev kit lacks is a *transceiver*: CAN_TX/CAN_RX are on the **unpopulated J17 header** (solder pins yourself) and need an external 3.3V transceiver (e.g., SN65HVD230). A SPI-based CAN adapter (MCP2515/MCP2518FD) is the simpler plug-and-play path via the 40-pin header's SPI pins + device-tree overlay.
- **Gateway modules on modern (esp. German/EV, roughly 2018+) cars may block raw CAN at the OBD-II port.** 2008–2017 cars usually expose the powertrain CAN directly on pins 6/14. (Note: the companion research doc confirms the 2017 Sonata LF has NO gateway blocking — raw C-CAN is on the port.)
- **Best reference architecture:** openpilot's `CarState` (wheel speeds → `vEgo` Kalman filter, `steeringAngleDeg`, `yawRate`, `brakePressed`, blinkers, `gasPressed`...) — exactly the signal set an LDW/FCW fusion loop needs.

## SAE J1979 OBD-II standard PIDs — what is standardized and its limits

Key Mode 01 PIDs (hex): 0x0C RPM (((A·256)+B)/4), 0x0D vehicle speed (A, 0–255 km/h), 0x04 engine load, 0x05 coolant temp, 0x0B intake manifold pressure, 0x0F intake air temp, 0x10 MAF, 0x11 throttle position, 0x2F fuel level, 0x42 module voltage, 0x46 ambient temp, 0x00 supported-PIDs bitmap. Typical vehicle implements 40–80 of ~200 defined PIDs.

**Limits:** J1979 standardizes **none** of: steering angle, steering rate, yaw rate, lateral/longitudinal accel, individual wheel speeds, brake pedal position/pressure, turn-signal state, gear. For LDW/FCW, J1979 can supply **vehicle speed (0x0D)** and **throttle/RPM** — everything else requires proprietary frame decoding.

## Manufacturer-proprietary CAN frames & reverse engineering workflow

1. **Capture** raw frames (`candump -L can0`) with the car awake.
2. **Exercise one control at a time** (steering lock-to-lock, brake, blinker, throttle) and diff captures.
3. **Tools:** cabana (https://github.com/commaai/openpilot/blob/HEAD/tools/cabana/README.md), SavvyCAN, `cansniffer` (can-utils), `cantools decode/plot`.
4. A **DBC file** maps `ID → message → signals`: `SG_ <name> : <startbit>|<len>@<endian><sign> (<factor>,<offset>) [min|max] "<unit>"`.

## comma.ai opendbc — the project to use

- `opendbc/dbc/` holds the DBC files; `opendbc/car/<brand>/` holds per-brand ports (`carstate.py` decodes the CAN stream into normalized vehicle state); `opendbc/can/` holds the `CANParser`/`CANPacker` engine.
- **Coverage:** 397 cars as of v0.3.1 (2026-04-22). Toyota, Honda, Hyundai/Kia, Ford, GM, VW/Audi/Porsche, BMW, Tesla, Rivian, Subaru, Nissan, Mazda, Volvo, PSA/Stellantis.
- **How to use a DBC:** `git clone https://github.com/commaai/opendbc`, then `cantools decode opendbc/dbc/<car>.dbc` on a candump log, or opendbc's `CANParser` in Python pointed at the DBC + message/signal list (the same pattern `carstate.py` uses).

## Signals that matter for LDW/FCW, with typical on-bus update rates

Core fusion set (from openpilot's `CarState`): **speed + wheel speeds (v_ego, standstill), steering angle/rate, yaw rate, brake pressed, turn signals**.

| Signal | Typical rate | Notes |
|---|---|---|
| Vehicle speed | 10–100 Hz | OBD-II 0x0D fallback at ~1–10 Hz only |
| Wheel speeds ×4 | 50–100 Hz | |
| Steering angle (+rate) | 50–100 Hz | |
| Yaw rate | ~50 Hz | |
| Brake pedal / pressure | 50–100 Hz | |
| Turn signals | event-driven / low | suppress LDW during lane changes |
| Gas pedal | 50–100 Hz | |
| Gear | 10–20 Hz | |
| Engine RPM | ~100 Hz | broadcast on many cars |

## Data throughput reality check

**Path (a) OBD-II diagnostic polling:** request/response per PID (ID 0x7DF → 0x7E8+). ~1–10 Hz per PID, tens–hundreds of ms per cycle, ~10–40 PID reads/sec aggregate. **Do not design the warning loop around polled PIDs.** Use only as fallback speed source.

**Path (b) Passive CAN sniffing:** listen-only at the bus bit rate (500 kbps typical). You see **100% of traffic on the wired bus segment** — real cars run ~20–50% bus load, i.e. **1,000–2,000 frames/sec**. Signals at 10–100 Hz, timestamped at arrival, few-ms latency. MCP2515 at 10 MHz SPI keeps up with 500 kbps RX comfortably; native MTTCAN even more so.

**Gateway check:** plug in, `candump can0`, count frames. Hundreds+/sec = healthy bus; <10/sec of only 0x7xx IDs = gateway filtering.

## Wiring notes

### OBD-II (SAE J1962) 16-pin, vehicle side looking into the socket

```
 1  2  3  4  5  6  7  8
 9 10 11 12 13 14 15 16
```

| Pin | Function | Wire to |
|---|---|---|
| 4 | Chassis ground | Adapter GND (tie with pin 5) |
| 5 | Signal ground | Adapter GND |
| 6 | **CAN High** | Transceiver CANH |
| 14 | **CAN Low** | Transceiver CANL |
| 16 | +12 V constant | **Cap off / leave unused** — always live |

### Practical checklist
1. **Polarity matters.** CANH↔CANL swapped = silent bus. If `candump` shows nothing and error counters climb, swap H/L first.
2. **Ground is not optional.** Tie OBD pins 4+5 to adapter/Jetson ground. Continuity-check cheap pigtails with a multimeter.
3. **Termination:** the car provides it (~60 Ω across CANH/CANL with car asleep). **Turn OFF / remove any termination jumper on your adapter** — a third terminator breaks the bus.
4. **Pin 16:** heat-shrink and stow.
5. **Car must be awake:** key to RUN or engine running. Key-off silence is normal.
6. **Listen-only first** so a misconfigured node can't disturb the vehicle bus.

### Jetson Orin Nano (Super) dev kit CAN hookup — two options

**Option 1 — SPI CAN adapter (recommended, simplest).** MCP2515/MCP2518FD module on the 40-pin header's SPI1 pins (MOSI 19 / MISO 21 / SCLK 23 / CS0 24) + INT GPIO + 3.3V/GND, with a device-tree overlay enabling the driver on the right SPI bus. Then plain SocketCAN: `ip link set can0 up type can bitrate 500000`.

**Option 2 — native SoC CAN (no SPI adapter).** T234 has two MTTCAN controllers; the dev kit exposes **CAN0** on the **unpopulated 4-pin J17 header**: J17-1 = CAN_TX, J17-2 = CAN_RX, J17-3 = GND, J17-4 = 3.3V. Solder a header, wire a **3.3V transceiver** (SN65HVD230: TXD←CAN_TX, RXD→CAN_RX, VCC 3.3V, GND; CANH/CANL→OBD 6/14), un-block the `mttcan` kernel module (blacklisted by default on JetPack 6.x), set pinmux for module pins 143/145 manually (`jetson-io` does not manage J17), then bring up `can0`.

**Kernel/OS:** JetPack 5.x/6.x ships SocketCAN + `mttcan`; `can-utils` is apt-installable. JetPack 6.x blacklists `mttcan` by default.

## Curated project links

- **comma.ai opendbc** — https://github.com/commaai/opendbc — DBC database + carstate decoders; source of the Sonata DBC
- **comma.ai openpilot** — https://github.com/commaai/openpilot — reference architecture: camera CV + CarState fusion at real-time rates
- **cabana** — https://github.com/commaai/openpilot/blob/HEAD/tools/cabana/README.md — CAN visualizer/reverse-engineering with opendbc integration
- **vietanhdev/open-adas** — https://github.com/vietanhdev/open-adas — Jetson Nano ADAS prototype (FCW + LDW + traffic sign, camera + CAN reader)
- **holtzj/openaaadas** — https://github.com/holtzj/openaaadas — open-adas ported to Jetson Orin Nano, JetPack 6.2 / TensorRT 10
- **trinhdinhphuong/car-smart-cam** — https://github.com/trinhdinhphuong/car-smart-cam — Jetson Nano ADAS with hardware/software write-ups
- **python-can** — https://github.com/hardbyte/python-can — Python SocketCAN library
- **cantools** — https://github.com/cantools/cantools — DBC parse/decode/encode, candump-pipe decoding
- **SavvyCAN** — https://github.com/collin80/SavvyCAN — cross-platform CAN GUI
- **can-utils** — https://github.com/linux-can/can-utils — `candump`, `cansend`, `cansniffer`, `cangen`
- **python-obd** — https://github.com/brendan-w/python-OBD — J1979 PID fallback only
- **lansalot/canbusdbc** — https://github.com/lansalot/canbusdbc — community DBC collection
- **aria-karimi/jetson-nano-waveshare-can** — https://github.com/aria-karimi/jetson-nano-waveshare-can — Waveshare MCP2515 board bring-up on Jetson
