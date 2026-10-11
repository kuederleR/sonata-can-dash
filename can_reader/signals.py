"""Data-driven CAN signal definitions for hyundai_2015_ccan (Sonata LF).

Adding a signal is a table edit here — not decoder surgery.
All layouts are Intel (little-endian) bit numbering matching the DBC `@1` form.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SignalSpec:
    name: str
    start_bit: int
    length: int
    factor: float = 1.0
    offset: float = 0.0
    signed: bool = False


@dataclass(frozen=True)
class MessageSpec:
    can_id: int
    name: str
    signals: tuple[SignalSpec, ...]


# --- Message / signal table (from docs/RESEARCH-sonata-2017-lf.md §B + DBC) ---

CLU11 = MessageSpec(
    can_id=0x4F1,
    name="CLU11",
    signals=(
        SignalSpec("CF_Clu_Vanz", start_bit=8, length=9, factor=0.5),
        SignalSpec("CF_Clu_SPEED_UNIT", start_bit=17, length=1),
    ),
)

WHL_SPD11 = MessageSpec(
    can_id=0x386,
    name="WHL_SPD11",
    signals=(
        SignalSpec("WHL_SPD_FL", start_bit=0, length=14, factor=0.03125),
        SignalSpec("WHL_SPD_FR", start_bit=16, length=14, factor=0.03125),
        SignalSpec("WHL_SPD_RL", start_bit=32, length=14, factor=0.03125),
        SignalSpec("WHL_SPD_RR", start_bit=48, length=14, factor=0.03125),
        SignalSpec("WHL_SPD_AliveCounter_LSB", start_bit=14, length=2),
        SignalSpec("WHL_SPD_AliveCounter_MSB", start_bit=30, length=2),
        SignalSpec("WHL_SPD_Checksum_LSB", start_bit=46, length=2),
        SignalSpec("WHL_SPD_Checksum_MSB", start_bit=62, length=2),
    ),
)

SAS11 = MessageSpec(
    can_id=0x2B0,
    name="SAS11",
    signals=(
        SignalSpec("SAS_Angle", start_bit=0, length=16, factor=0.1, signed=True),
        SignalSpec("SAS_Speed", start_bit=16, length=8, factor=4.0),
    ),
)

TCS13 = MessageSpec(
    can_id=0x394,
    name="TCS13",
    signals=(
        SignalSpec("aBasis", start_bit=0, length=11, factor=0.01, offset=-10.23),
        SignalSpec("BrakeLight", start_bit=11, length=1),
        SignalSpec("DriverOverride", start_bit=45, length=2),
        SignalSpec("StandStill", start_bit=47, length=1),
        SignalSpec("PBRAKE_ACT", start_bit=53, length=1),
        SignalSpec("DriverBraking", start_bit=55, length=1),
    ),
)

CGW1 = MessageSpec(
    can_id=0x541,
    name="CGW1",
    signals=(
        SignalSpec("CF_Gway_TurnSigLh", start_bit=19, length=2),
        SignalSpec("CF_Gway_TurnSigRh", start_bit=62, length=2),
    ),
)

EMS16 = MessageSpec(
    can_id=0x260,
    name="EMS16",
    signals=(SignalSpec("CF_Ems_AclAct", start_bit=62, length=2),),
)

# EMS11 carries engine speed (N). EMS12 carries pedal + BRAKE_ACT.
# Prefer TCS13 DriverOverride==2 when present; many no-ADAS OBD taps
# never see TCS13, so EMS12 BRAKE_ACT is the fallback (always assign 0/1).
EMS11 = MessageSpec(
    can_id=0x316,
    name="EMS11",
    signals=(SignalSpec("N", start_bit=16, length=16, factor=0.25),),
)

EMS12 = MessageSpec(
    can_id=0x329,
    name="EMS12",
    signals=(
        SignalSpec("BRAKE_ACT", start_bit=32, length=2),
        SignalSpec("PV_AV_CAN", start_bit=48, length=8, factor=0.3906),
    ),
)

EMS15 = MessageSpec(
    can_id=0x547,
    name="EMS15",
    signals=(SignalSpec("FA_PV_CAN", start_bit=8, length=8, factor=0.3906),),
)

# Sonata LF is TCU_GEARS in openpilot — prefer TCU12 CUR_GR / TCU11 G_SEL_DISP.
TCU12 = MessageSpec(
    can_id=0x112,
    name="TCU12",
    signals=(SignalSpec("CUR_GR", start_bit=8, length=4),),
)

TCU11 = MessageSpec(
    can_id=0x111,
    name="TCU11",
    signals=(SignalSpec("G_SEL_DISP", start_bit=8, length=4),),
)

LVR11 = MessageSpec(
    can_id=0x354,
    name="LVR11",
    signals=(SignalSpec("CF_Lvr_GearInf", start_bit=0, length=4),),
)

LVR12 = MessageSpec(
    can_id=0x367,
    name="LVR12",
    signals=(SignalSpec("CF_Lvr_Gear", start_bit=32, length=4),),
)

MDPS12 = MessageSpec(
    can_id=0x251,
    name="MDPS12",
    signals=(
        SignalSpec(
            "CR_Mdps_StrColTq",
            start_bit=0,
            length=11,
            factor=0.0078125,
            offset=-8.0,
        ),
    ),
)

CLU12 = MessageSpec(
    can_id=0x5B0,
    name="CLU12",
    signals=(SignalSpec("CF_Clu_Odometer", start_bit=0, length=24, factor=0.1),),
)

MESSAGES: tuple[MessageSpec, ...] = (
    CLU11,
    WHL_SPD11,
    SAS11,
    TCS13,
    CGW1,
    EMS16,
    EMS11,
    EMS12,
    EMS15,
    TCU12,
    TCU11,
    LVR11,
    LVR12,
    MDPS12,
    CLU12,
)

MESSAGES_BY_ID: dict[int, MessageSpec] = {m.can_id: m for m in MESSAGES}

# Friendly names for dashboard "which IDs are alive" strip
WATCHED_IDS: dict[int, str] = {
    0x386: "WHL_SPD",
    0x2B0: "SAS",
    0x394: "TCS13",
    0x153: "TCS11",
    0x38A: "ABS11",
    0x316: "EMS11",
    0x329: "EMS12",
    0x260: "EMS16",
    0x81: "EMS_DCT12",
    0x113: "TCU13",
    0x492: "EMS19",
    0x547: "EMS15",
    0x112: "TCU12",
    0x111: "TCU11",
    0x354: "LVR11",
    0x367: "LVR12",
    0x541: "CGW1",
}
