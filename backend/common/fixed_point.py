from decimal import Decimal, ROUND_HALF_UP


SCALE = 1_000_000


def encode(value: int | float | Decimal, scale: int = SCALE) -> int:
    if scale <= 0:
        raise ValueError("scale must be positive")
    return int((Decimal(str(value)) * scale).to_integral_value(rounding=ROUND_HALF_UP))


def decode(value: int, scale: int = SCALE) -> float:
    if scale <= 0:
        raise ValueError("scale must be positive")
    return float(Decimal(value) / Decimal(scale))


def encode_values(values: list[int | float | Decimal], scale: int = SCALE) -> list[int]:
    return [encode(value, scale) for value in values]


def decode_values(values: list[int], scale: int = SCALE) -> list[float]:
    return [decode(value, scale) for value in values]
