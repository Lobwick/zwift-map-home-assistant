import struct

import pytest
from zwift_map_pure.protobuf import DecodeError, decode_fields, parse_player_state


def varint(value: int) -> bytes:
    if value < 0:
        value += 1 << 64  # int32/int64 negatives are sign-extended to 64 bits
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def field_varint(number: int, value: int) -> bytes:
    return varint(number << 3) + varint(value)


def field_float(number: int, value: float) -> bytes:
    return varint(number << 3 | 5) + struct.pack("<f", value)


def field_bytes(number: int, value: bytes) -> bytes:
    return varint(number << 3 | 2) + varint(len(value)) + value


def int32_wire(value: int) -> int:
    """How an unsigned 32-bit id ends up in an int32 protobuf field."""
    return value - (1 << 32) if value >= 1 << 31 else value


def sample_state(route_id: int = 2947111049) -> bytes:
    return b"".join(
        [
            field_varint(1, 1234567),
            field_varint(2, 987654321),
            field_varint(3, 15320),
            field_varint(6, 32_500_000),  # 32.5 km/h in mm/h
            field_varint(9, 1_500_000),  # 90 rpm in micro-Hz
            field_varint(11, 142),
            field_varint(12, 251),
            field_varint(19, (6 << 16) | 4),  # course 6, forward
            field_varint(20, 23 << 8),  # road 23
            field_float(25, 12345.0),
            field_float(26, 9100.0),
            field_float(27, -6789.0),
            field_bytes(30, b"ignored"),
            field_varint(35, 1),
            field_varint(39, int32_wire(route_id)),
        ]
    )


def test_parse_player_state_fields():
    state = parse_player_state(sample_state())
    assert state.player_id == 1234567
    assert state.distance_m == 15320
    assert state.speed_kmh == pytest.approx(32.5)
    assert state.cadence_rpm == 90
    assert state.heart_rate == 142
    assert state.power_w == 251
    assert state.course_id == 6
    assert state.is_forward
    assert state.road_id == 23
    assert state.x_m == pytest.approx(123.45)
    assert state.z_m == pytest.approx(-67.89)
    assert state.altitude_m == pytest.approx(50.0)
    assert state.world_id == 1
    assert state.is_active


def test_route_id_above_int32_range_is_unsigned():
    # Big Loop's id (2947111049) does not fit an int32 and arrives negative.
    assert parse_player_state(sample_state(2947111049)).route_id == 2947111049
    assert parse_player_state(sample_state(240388043)).route_id == 240388043


def test_missing_fields_default_to_zero():
    state = parse_player_state(field_varint(1, 42))
    assert state.route_id == 0
    assert state.world_id == 0
    assert not state.is_active


def test_truncated_buffer_raises():
    with pytest.raises(DecodeError):
        decode_fields(sample_state()[:-1])
