"""Minimal protobuf wire-format decoder for Zwift's relay ``PlayerState``.

The generated ``*_pb2`` modules shipped with older Zwift client libraries do not
load with current protobuf runtimes and do not know the newer fields (world,
route). Decoding the wire format directly keeps this integration free of
generated code and of any protobuf dependency.

Field numbers follow the community reverse-engineering of the Zwift protocol
(see the zwift-offline project, ``protobuf/udp-node-msgs.proto``).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

# Wire types
_VARINT = 0
_FIXED64 = 1
_LEN = 2
_FIXED32 = 5

# PlayerState field numbers
F_ID = 1
F_WORLD_TIME = 2
F_DISTANCE = 3
F_ROAD_TIME = 4
F_LAPS = 5
F_SPEED = 6
F_CADENCE_UHZ = 9
F_HEARTRATE = 11
F_POWER = 12
F_CLIMBING = 15
F_TIME = 16
F_F19 = 19
F_AUX3 = 20
F_CALORIES = 24
F_X = 25
F_Y_ALTITUDE = 26
F_Z = 27
F_GROUP_ID = 29
F_SPORT = 31
F_WORLD = 35
F_ROUTE = 39

_FLOAT_FIELDS = {F_X, F_Y_ALTITUDE, F_Z}


class DecodeError(ValueError):
    """Raised when the buffer is not a valid protobuf message."""


def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if pos >= len(buf):
            raise DecodeError("truncated varint")
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
        if shift > 63:
            raise DecodeError("varint too long")


def decode_fields(buf: bytes) -> dict[int, int | float | bytes]:
    """Decode a flat protobuf message into ``{field_number: value}``.

    Varints are returned as unsigned 64-bit integers, fixed32 fields listed in
    ``_FLOAT_FIELDS`` as floats, other fixed fields as integers and
    length-delimited fields as raw bytes. Repeated fields keep the last value.
    """
    fields: dict[int, int | float | bytes] = {}
    pos = 0
    end = len(buf)
    while pos < end:
        key, pos = _read_varint(buf, pos)
        number, wire_type = key >> 3, key & 0x7
        if number == 0:
            raise DecodeError("field number 0")
        if wire_type == _VARINT:
            value, pos = _read_varint(buf, pos)
        elif wire_type == _FIXED32:
            if pos + 4 > end:
                raise DecodeError("truncated fixed32")
            chunk = buf[pos : pos + 4]
            pos += 4
            value = (
                struct.unpack("<f", chunk)[0]
                if number in _FLOAT_FIELDS
                else struct.unpack("<I", chunk)[0]
            )
        elif wire_type == _FIXED64:
            if pos + 8 > end:
                raise DecodeError("truncated fixed64")
            value = struct.unpack("<Q", buf[pos : pos + 8])[0]
            pos += 8
        elif wire_type == _LEN:
            length, pos = _read_varint(buf, pos)
            if pos + length > end:
                raise DecodeError("truncated length-delimited field")
            value = buf[pos : pos + length]
            pos += length
        else:
            raise DecodeError(f"unsupported wire type {wire_type}")
        fields[number] = value
    return fields


def _signed64(value: int) -> int:
    return value - (1 << 64) if value >= 1 << 63 else value


@dataclass(frozen=True, slots=True)
class PlayerState:
    """The parts of Zwift's ``PlayerState`` this integration uses."""

    player_id: int
    world_time_ms: int
    distance_m: int
    road_time: int
    laps: int
    speed_kmh: float
    cadence_rpm: int
    heart_rate: int
    power_w: int
    climbing_m: int
    time_s: int
    f19: int
    aux3: int
    calories: int
    x_m: float
    z_m: float
    altitude_m: float
    group_id: int
    sport: int
    world_id: int
    route_id: int

    @property
    def course_id(self) -> int:
        """Course (map) id packed into field 19."""
        return (self.f19 & 0xFF0000) >> 16

    @property
    def is_forward(self) -> bool:
        """Whether the rider travels in the road's forward direction."""
        return bool(self.f19 & 4)

    @property
    def road_id(self) -> int:
        """Physical road the rider is on, packed into field 20."""
        return (self.aux3 & 0xFF00) >> 8

    @property
    def in_event(self) -> bool:
        """Riders in an event (group ride, race) carry a group id."""
        return self.group_id != 0

    @property
    def is_active(self) -> bool:
        """A state with no clock and no distance is an empty placeholder."""
        return self.world_time_ms > 0 or self.distance_m > 0


def parse_player_state(buf: bytes) -> PlayerState:
    """Decode a relay ``PlayerState`` buffer."""
    f = decode_fields(buf)

    def num(field: int) -> int:
        value = f.get(field, 0)
        return int(value) if isinstance(value, (int, float)) else 0

    def flt(field: int) -> float:
        value = f.get(field, 0.0)
        return float(value) if isinstance(value, (int, float)) else 0.0

    # The route id is an int32 on the wire; ids above 2**31 arrive as negative
    # numbers sign-extended to 64 bits. Zwift catalogues them as unsigned.
    route_id = num(F_ROUTE) & 0xFFFFFFFF

    return PlayerState(
        player_id=_signed64(num(F_ID)),
        world_time_ms=_signed64(num(F_WORLD_TIME)),
        distance_m=_signed64(num(F_DISTANCE)),
        road_time=_signed64(num(F_ROAD_TIME)),
        laps=num(F_LAPS),
        speed_kmh=num(F_SPEED) / 1_000_000,
        cadence_rpm=round(num(F_CADENCE_UHZ) * 60 / 1_000_000),
        heart_rate=num(F_HEARTRATE),
        power_w=num(F_POWER),
        climbing_m=num(F_CLIMBING),
        time_s=num(F_TIME),
        f19=num(F_F19),
        aux3=num(F_AUX3),
        calories=num(F_CALORIES),
        x_m=flt(F_X) / 100,
        z_m=flt(F_Z) / 100,
        altitude_m=(flt(F_Y_ALTITUDE) - 9000) / 2,
        group_id=_signed64(num(F_GROUP_ID)),
        sport=num(F_SPORT),
        world_id=num(F_WORLD),
        route_id=route_id,
    )
