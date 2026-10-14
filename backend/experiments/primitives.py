from __future__ import annotations

import json
import random
import secrets
from typing import Any

from common.secret_sharing import PRIME, from_field, to_field


class ExperimentRandom:
    def __init__(self, seed: int | None = None):
        self.seed = seed
        self.source = random.Random(seed) if seed is not None else secrets.SystemRandom()

    def gamma_difference(self, sensitivity: float, epsilon: float, participants: int = 1) -> float:
        if sensitivity <= 0 or epsilon <= 0 or participants <= 0:
            raise ValueError("sensitivity, epsilon and participants must be positive")
        shape = 1.0 / participants
        scale = sensitivity / epsilon
        return self.source.gammavariate(shape, scale) - self.source.gammavariate(shape, scale)

    def split_secret(self, value: int) -> tuple[int, int]:
        secret = to_field(value)
        while True:
            first = self.source.randrange(PRIME)
            second = (secret - first) % PRIME
            if first != secret and second != secret:
                return first, second


def reconstruct(first: int, second: int) -> int:
    return from_field((first + second) % PRIME)


def serialized_size(payload: Any) -> int:
    return len(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    )
