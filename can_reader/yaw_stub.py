"""
Yaw-rate placeholder.

KNOWN GAP: yaw rate is not decoded on the 2017 Sonata LF with hyundai_2015_ccan.
ESP12 (0x145) likely exists on the wire but is undecoded in the DBC.

Future work (do not invent a decoder here):
  - Derive yaw from SAS_Angle + wheel speeds via a kinematic bicycle model, or
  - Fuse a Jetson-side IMU, or
  - Reverse-engineer ESP12 offline and add a SignalSpec row.

This module exists so callers have an explicit stub to import / replace later.
"""

from __future__ import annotations


def yaw_rate_deg_s() -> None:
    """Stub: always returns None until a derived-yaw / IMU module lands."""
    return None
