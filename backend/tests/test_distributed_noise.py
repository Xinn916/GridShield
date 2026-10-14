import random
import statistics

import pytest

from common.distributed_noise import DistributedLaplaceNoise


def aggregate_samples(participants: int, samples: int, seed: int) -> list[float]:
    generator = DistributedLaplaceNoise(random.Random(seed))
    return [
        sum(generator.partial_noise(2.0, 1.0, participants) for _ in range(participants))
        for _ in range(samples)
    ]


def test_aggregated_gamma_difference_noise_has_near_zero_mean() -> None:
    values = aggregate_samples(participants=3, samples=20_000, seed=2026)
    assert statistics.mean(values) == pytest.approx(0.0, abs=0.08)


def test_aggregated_noise_variance_matches_laplace_theory() -> None:
    values = aggregate_samples(participants=3, samples=30_000, seed=2027)
    theoretical_variance = 2 * (2.0 / 1.0) ** 2
    assert statistics.pvariance(values) == pytest.approx(theoretical_variance, rel=0.08)


def test_aggregate_scale_is_stable_across_participant_counts() -> None:
    variances = [
        statistics.pvariance(aggregate_samples(participants, 20_000, 2100 + participants))
        for participants in (1, 3, 10)
    ]
    theoretical_variance = 8.0
    assert all(value == pytest.approx(theoretical_variance, rel=0.12) for value in variances)


def test_each_vector_bucket_matches_the_target_laplace_variance() -> None:
    participants = 3
    samples = 8_000
    generators = [DistributedLaplaceNoise(random.Random(3000 + index)) for index in range(participants)]
    bucket_samples = [[], [], []]
    for _ in range(samples):
        partials = [
            generator.partial_noise_vector(3, 2.0, 1.0, participants)
            for generator in generators
        ]
        for bucket_index in range(3):
            bucket_samples[bucket_index].append(
                sum(values[bucket_index] for values in partials)
            )
    assert all(statistics.mean(values) == pytest.approx(0.0, abs=0.15) for values in bucket_samples)
    assert all(statistics.pvariance(values) == pytest.approx(8.0, rel=0.15) for values in bucket_samples)
