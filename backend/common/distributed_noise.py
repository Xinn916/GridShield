import secrets
from typing import Protocol


class GammaRandom(Protocol):
    def gammavariate(self, alpha: float, beta: float) -> float: ...


class DistributedLaplaceNoise:
    def __init__(self, rng: GammaRandom | None = None):
        self.rng = rng or secrets.SystemRandom()

    def partial_noise(self, sensitivity: float, epsilon: float, participants: int) -> float:
        if sensitivity <= 0:
            raise ValueError("sensitivity must be positive")
        if epsilon <= 0:
            raise ValueError("epsilon must be positive")
        if participants <= 0:
            raise ValueError("participants must be positive")
        shape = 1.0 / participants
        scale = sensitivity / epsilon
        positive = self.rng.gammavariate(shape, scale)
        negative = self.rng.gammavariate(shape, scale)
        return positive - negative

    def partial_noise_vector(
        self, bucket_count: int, sensitivity: float, epsilon: float, participants: int
    ) -> list[float]:
        if bucket_count <= 0:
            raise ValueError("bucket_count must be positive")
        return [
            self.partial_noise(sensitivity, epsilon, participants)
            for _ in range(bucket_count)
        ]
