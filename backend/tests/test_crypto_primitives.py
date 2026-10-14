import math

from common.fixed_point import SCALE, decode, decode_values, encode, encode_values
from common.secret_sharing import (
    reconstruct_secret,
    reconstruct_secrets,
    split_secret,
    split_secrets,
    to_field,
)


def test_scalar_secret_reconstructs() -> None:
    first, second = split_secret(123456789)
    assert reconstruct_secret(first, second) == 123456789


def test_array_secrets_reconstruct() -> None:
    values = [0, 1, 42, 999999]
    first, second = split_secrets(values)
    assert reconstruct_secrets(first, second) == values


def test_fixed_point_round_trip_error_is_bounded() -> None:
    values = [0.0, 0.1234564, 5.0, 12345.678901]
    decoded = decode_values(encode_values(values))
    assert all(math.isclose(actual, expected, abs_tol=0.5 / SCALE) for actual, expected in zip(decoded, values))


def test_negative_fixed_point_secret_reconstructs() -> None:
    encoded = encode(-12.345678)
    first, second = split_secret(encoded)
    assert decode(reconstruct_secret(first, second)) == -12.345678


def test_neither_share_directly_reveals_the_secret() -> None:
    secret = 987654321
    for _ in range(100):
        first, second = split_secret(secret)
        assert first != to_field(secret)
        assert second != to_field(secret)
