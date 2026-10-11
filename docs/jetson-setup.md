# Jetson Orin Nano Super — SocketCAN bring-up

Step-by-step from a bare Jetson to `candump can0` seeing Sonata C-CAN frames, then running this dashboard.

Target: **NVIDIA Jetson Orin Nano Super** with JetPack 5.x or 6.x. The builder's exact CAN adapter is unknown — any adapter that shows up as a SocketCAN interface works with this project.

## 0. Prerequisites

- Jetson flashed with JetPack (SDK Manager or SD image)
- Network access for `apt` / `pip`
- OBD-II pigtail wired per [wiring.md](wiring.md)
- Car awake (key RUN or engine on) when testing live

## 1. Base packages

```bash
sudo apt update
sudo apt install -y can-utils python3-venv python3-pip iproute2
```

Confirm SocketCAN userspace tools:

```bash
candump -h
ip link help can
```

## 2. Bring up `can0` — pick one path

### Option A — SPI CAN adapter (recommended)

MCP2515 or MCP2518FD on the 40-pin header:

| Function | 40-pin |
|---|---|
| MOSI | 19 |
| MISO | 21 |
| SCLK | 23 |
| CS0 | 24 |
| INT | a free GPIO (board-specific) |
| 3.3V / GND | 1 or 17 / 6 |

1. Enable the overlay for your board (often via `sudo /opt/nvidia/jetson-io/jetson-io.py`, or a vendor dtoverlay). Waveshare / similar HAT docs usually name the overlay explicitly.
2. Reboot so `can0` appears: `ip link show can0`
3. Bring the link up **listen-only first** at 500 kbps:

```bash
sudo ip link set can0 down
sudo ip link set can0 up type can bitrate 500000 listen-only on
```

`listen-only on` ensures the controller will not ACK or transmit — matching this project's never-transmit rule.

### Option B — Native MTTCAN via J17

The T234 SoC has MTTCAN. The Orin Nano Super **dev kit** exposes CAN0 on the **unpopulated J17** header:

| J17 pin | Signal |
|---|---|
| 1 | CAN_TX |
| 2 | CAN_RX |
| 3 | GND |
| 4 | 3.3V |

1. Solder a 4-pin header onto J17.
2. Wire a **3.3V** transceiver (e.g. SN65HVD230):
   - TXD ← CAN_TX, RXD → CAN_RX, VCC 3.3V, GND
   - CANH / CANL → OBD pins 6 / 14
3. JetPack 6.x blacklists `mttcan` by default. Edit `/etc/modprobe.d/` (remove or comment the blacklist line for `mttcan`), then:

```bash
sudo modprobe mttcan
```

4. Pinmux for module pins **143 / 145** must be set for CAN — `jetson-io` does **not** manage J17. Use the pinmux spreadsheet / `busybox devmem` recipes from NVIDIA Orin Nano CAN notes for your JetPack revision, or a vendor script.
5. Bring up listen-only:

```bash
sudo ip link set can0 down
sudo ip link set can0 up type can bitrate 500000 listen-only on
```

## 3. Verify with candump

```bash
candump can0
```

Expect hundreds of frames/sec with IDs such as `386`, `2B0`, `394`, `4F1`, `541`, `260`, `354` when the car is awake. Silence with key-off is normal. If you see nothing and error counters climb, swap CAN-H/CAN-L (see [wiring.md](wiring.md)).

Optional ASCII log for later replay tooling:

```bash
candump -L can0 > /tmp/sonata.candump
```

## 4. Python venv + this project

```bash
cd /path/to/sonata-can-dash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Simulator first (no car):

```bash
python run.py --simulate
```

Open `http://<jetson-ip>:8080` on your phone (same Wi-Fi or phone hotspot).

Live car:

```bash
python run.py --channel can0 --bitrate 500000
```

Gear enum calibration (once, on the car):

```bash
python -m can_reader.calibrate_gear --channel can0
```

## 5. systemd service

Copy the unit and adjust paths/user:

```bash
sudo cp systemd/sonata-can-dash.service /etc/systemd/system/
sudo systemctl edit --full sonata-can-dash.service   # set WorkingDirectory / User / ExecStart
sudo systemctl daemon-reload
sudo systemctl enable --now sonata-can-dash.service
sudo systemctl status sonata-can-dash.service
```

Bring `can0` up before the service (a oneshot unit or `/etc/network/interfaces` snippet). Example oneshot:

```bash
sudo ip link set can0 up type can bitrate 500000 listen-only on
```

## JetPack notes

- JetPack 5.x / 6.x both ship SocketCAN. Prefer the JetPack version your camera/CUDA stack already needs.
- JetPack 6.x: `mttcan` blacklisted by default (Option B).
- SPI adapters (Option A) avoid J17 soldering and pinmux pain; use them unless you specifically want native CAN.

## Troubleshooting

| Symptom | Check |
|---|---|
| No `can0` | Overlay / `mttcan` / cabling |
| `candump` empty, errors up | Polarity H/L, ground, car awake, bitrate 500k |
| Frames but dashboard stale | `python run.py` running? firewall? phone on same LAN? |
| Checksum errors climbing | Noisy wiring / wrong DLC; decoder still shows speeds |
