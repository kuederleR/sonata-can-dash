"""WHL_SPD11 (0x386) alive-counter / checksum helpers.

Checksum algorithm from opendbc/openpilot Hyundai safety tests:
sum all data bits except counter and checksum bits, XOR 9, mask to 4 bits.

Counter: byte1 bits 6-7 (LSB), byte3 bits 6-7 (MSB)
Checksum: byte5 bits 6-7 (LSB), byte7 bits 6-7 (MSB)
"""

from __future__ import annotations

WHL_SPD11_ID = 0x386


def whl_spd11_checksum(data: bytes | bytearray) -> int:
    """Compute the expected 4-bit WHL_SPD11 checksum for an 8-byte payload."""
    if len(data) < 8:
        data = bytes(data) + bytes(8 - len(data))
    chksum = 0
    for i, b in enumerate(data[:8]):
        for j in range(8):
            # Exclude counter/checksum nibbles in the high 2 bits of bytes 1,3,5,7
            if i in (1, 3, 5, 7) and j >= 6:
                continue
            chksum += (b >> j) & 1
    return (chksum ^ 9) & 0xF


def extract_whl_spd11_checksum(data: bytes | bytearray) -> int:
    """Read the 4-bit checksum nibble from a WHL_SPD11 frame."""
    if len(data) < 8:
        return -1
    lsb = (data[5] >> 6) & 0x3
    msb = (data[7] >> 6) & 0x3
    return lsb | (msb << 2)


def validate_whl_spd11(data: bytes | bytearray) -> bool:
    """Return True if checksum matches. Never raises."""
    if len(data) < 8:
        return False
    return extract_whl_spd11_checksum(data) == whl_spd11_checksum(data)


def apply_whl_spd11_checksum(data: bytearray) -> bytearray:
    """Write a valid checksum into an 8-byte WHL_SPD11 payload (for simulator)."""
    while len(data) < 8:
        data.append(0)
    data[5] &= 0x3F
    data[7] &= 0x3F
    chk = whl_spd11_checksum(data)
    data[5] |= (chk & 0x3) << 6
    data[7] |= (chk & 0xC) << 4  # high 2 bits → byte7 bits 6-7
    return data
