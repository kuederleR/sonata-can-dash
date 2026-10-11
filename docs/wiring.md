# OBD-II ↔ Jetson CAN wiring

Passive sniff of the 2017 Sonata Limited (LF) **C-CAN** at **500 kbps** on OBD-II pins **6 / 14**. The car provides bus termination; your adapter must not add a third terminator.

## OBD-II pinout (vehicle socket, looking into the connector)

```
 1  2  3  4  5  6  7  8
 9 10 11 12 13 14 15 16
```

| Pin | Function | Wire to |
|---|---|---|
| 4 | Chassis ground | Adapter / transceiver GND (tie with pin 5) |
| 5 | Signal ground | Adapter / transceiver GND |
| 6 | **CAN High** | Transceiver CANH |
| 14 | **CAN Low** | Transceiver CANL |
| 16 | +12 V constant | **Do not use** — cap, heat-shrink, and stow |

## Transceiver wiring

### SPI adapter (MCP2515 / MCP2518FD module)

Most modules break out CANH / CANL / GND. Connect:

- CANH → OBD 6
- CANL → OBD 14
- GND → OBD 4+5 (and Jetson GND — common ground matters)
- Module logic side → Jetson 40-pin SPI as in [jetson-setup.md](jetson-setup.md)

**Termination:** turn **OFF** / remove the onboard 120 Ω jumper. The vehicle already presents ~60 Ω across CANH–CANL (two 120 Ω ends in parallel). A third terminator corrupts the bus.

### Native J17 + SN65HVD230 (example)

| SN65HVD230 | Connects to |
|---|---|
| TXD | J17 CAN_TX |
| RXD | J17 CAN_RX |
| VCC | 3.3 V (J17-4 or Jetson 3.3 V) |
| GND | J17 GND + OBD 4/5 |
| CANH | OBD 6 |
| CANL | OBD 14 |

Same rule: **no extra termination** on the transceiver board.

## Checklist before first live plug-in

1. **Polarity.** CANH↔CANL swapped = silent bus / climbing error counters. If `candump` is empty, swap H/L first.
2. **Common ground.** Continuity-check OBD 4 and 5 to adapter GND with a multimeter. Cheap pigtails are often miswired — verify before blaming software.
3. **Pin 16 capped.** Always hot; leave unused and insulated.
4. **Termination OFF** on the adapter.
5. **Listen-only first.** Bring the interface up with `listen-only on` (see [jetson-setup.md](jetson-setup.md)). This project's reader never calls `send()`, but the controller should still be listen-only so it cannot ACK.
6. **Car awake.** Key to RUN or engine running. Key-off silence is normal — ECUs sleep.

## Multimeter checks (cheap pigtails)

With the connector unplugged from the car:

- Continuity: pigtail pin 6 → your CANH wire
- Continuity: pigtail pin 14 → your CANL wire
- Continuity: pins 4 and 5 → GND wire
- **No** continuity from pin 16 to anything on the Jetson side

With the car asleep and adapter disconnected, resistance across OBD 6–14 at the vehicle port is typically ~60 Ω (two terminators). That is a sanity check that you are on the right pins — do not add another 120 Ω.

## Safety rules

- **Never transmit** on the vehicle bus for this project. Decode-only.
- Do not power the Jetson from OBD pin 16 unless you have designed a proper power path; prefer the Jetson's own supply.
- If anything on the car behaves oddly after connecting, unplug immediately and re-check polarity / termination.
