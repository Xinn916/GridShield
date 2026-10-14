import secrets
from collections.abc import Iterable


# Mersenne prime; comfortably larger than all encoded aggregates in this project.
PRIME = (1 << 127) - 1


def to_field(value: int) -> int:
    return value % PRIME


def from_field(value: int) -> int:
    normalized = value % PRIME
    return normalized - PRIME if normalized > PRIME // 2 else normalized


def split_secret(value: int) -> tuple[int, int]:
    secret = to_field(value)
    while True:
        share_1 = secrets.randbelow(PRIME)
        share_2 = (secret - share_1) % PRIME
        if share_1 != secret and share_2 != secret:
            return share_1, share_2


def reconstruct_secret(share_1: int, share_2: int) -> int:
    return from_field((share_1 + share_2) % PRIME)


def split_secrets(values: Iterable[int]) -> tuple[list[int], list[int]]:
    pairs = [split_secret(value) for value in values]
    return [pair[0] for pair in pairs], [pair[1] for pair in pairs]


def reconstruct_secrets(share_1: Iterable[int], share_2: Iterable[int]) -> list[int]:
    left = list(share_1)
    right = list(share_2)
    if len(left) != len(right):
        raise ValueError("share arrays must have equal length")
    return [reconstruct_secret(first, second) for first, second in zip(left, right)]
