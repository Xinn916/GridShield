import statistics

import pytest

from common.enums import OrganizationId, QueryType
from experiments.benchmark_runner import BenchmarkRunner, TrialExecutor, sensitivity_for
from experiments.models import BenchmarkConfig, ExperimentMode, PreparedStatistics
from experiments.primitives import ExperimentRandom
from experiments.run_benchmarks import integrity_snapshot


def prepared_stats(parties=None, window_cap=30.0) -> PreparedStatistics:
    parties = parties or [OrganizationId.ORG_A, OrganizationId.ORG_B, OrganizationId.ORG_C]
    sums = {party: float((index + 1) * 10) for index, party in enumerate(parties)}
    counts = {party: 10 for party in parties}
    return PreparedStatistics(
        parties=parties,
        local_sums=sums,
        local_counts=counts,
        unclipped_sum=sum(sums.values()) + 5,
        unclipped_count=sum(counts.values()),
        window_cap=window_cap,
        household_count=sum(counts.values()),
        local_query_time_ms=1.0,
        clipping_time_ms=0.4,
        peak_memory_kb=10.0,
    )


def test_experiment_secret_share_matches_plain_with_fixed_point_tolerance() -> None:
    prepared = prepared_stats()
    executor = TrialExecutor(ExperimentRandom(2026))
    plain = executor.execute(prepared, QueryType.SUM, ExperimentMode.PLAIN, 1.0)
    secret = executor.execute(prepared, QueryType.SUM, ExperimentMode.SECRET_SHARE, 1.0)
    assert secret.value == pytest.approx(plain.value, abs=1e-6)


def test_central_dp_noise_variance_matches_laplace_theory() -> None:
    rng = ExperimentRandom(3001)
    values = [rng.gamma_difference(2.0, 1.0, 1) for _ in range(30_000)]
    assert statistics.pvariance(values) == pytest.approx(8.0, rel=0.08)


def test_distributed_dp_noise_variance_matches_laplace_theory() -> None:
    rng = ExperimentRandom(3002)
    values = [
        sum(rng.gamma_difference(2.0, 1.0, 3) for _ in range(3))
        for _ in range(30_000)
    ]
    assert statistics.pvariance(values) == pytest.approx(8.0, rel=0.08)


def test_central_and_distributed_noise_have_similar_scale() -> None:
    central_rng = ExperimentRandom(3003)
    distributed_rng = ExperimentRandom(3004)
    central = [central_rng.gamma_difference(2.0, 1.0, 1) for _ in range(20_000)]
    distributed = [
        sum(distributed_rng.gamma_difference(2.0, 1.0, 3) for _ in range(3))
        for _ in range(20_000)
    ]
    assert statistics.pvariance(distributed) == pytest.approx(statistics.pvariance(central), rel=0.12)


def test_theoretical_noise_scale_decreases_with_epsilon() -> None:
    sensitivity = 30.0
    scales = [sensitivity / epsilon for epsilon in (0.1, 0.5, 1.0, 2.0, 4.0)]
    assert all(left > right for left, right in zip(scales, scales[1:]))


def test_experiment_sensitivities_use_count_one_and_supplied_window_cap() -> None:
    prepared = prepared_stats(window_cap=50.0)
    assert sensitivity_for(QueryType.COUNT, prepared) == 1.0
    assert sensitivity_for(QueryType.SUM, prepared) == 50.0


def test_fixed_seed_reproduces_private_results() -> None:
    prepared = prepared_stats()
    first = TrialExecutor(ExperimentRandom(42))
    second = TrialExecutor(ExperimentRandom(42))
    values_1 = [
        first.execute(prepared, QueryType.SUM, ExperimentMode.DISTRIBUTED_DP, 1.0).value
        for _ in range(10)
    ]
    values_2 = [
        second.execute(prepared, QueryType.SUM, ExperimentMode.DISTRIBUTED_DP, 1.0).value
        for _ in range(10)
    ]
    assert values_1 == values_2


def test_missing_seed_uses_nondeterministic_randomness() -> None:
    prepared = prepared_stats()
    first = TrialExecutor(ExperimentRandom())
    second = TrialExecutor(ExperimentRandom())
    values_1 = [first.execute(prepared, QueryType.COUNT, ExperimentMode.CENTRAL_DP, 1.0).value for _ in range(5)]
    values_2 = [second.execute(prepared, QueryType.COUNT, ExperimentMode.CENTRAL_DP, 1.0).value for _ in range(5)]
    assert values_1 != values_2


class FakeExperimentData:
    def prepare(self, parties, start_time, end_time, window_cap, household_count=None):
        count = min(household_count or len(parties) * 10, len(parties) * 10)
        per_party = max(1, count // len(parties))
        sums = {party: float((index + 1) * per_party) for index, party in enumerate(parties)}
        counts = {party: per_party for party in parties}
        return PreparedStatistics(
            parties=parties,
            local_sums=sums,
            local_counts=counts,
            unclipped_sum=sum(sums.values()),
            unclipped_count=sum(counts.values()),
            window_cap=window_cap,
            household_count=sum(counts.values()),
            local_query_time_ms=0.1,
            clipping_time_ms=0.05,
            peak_memory_kb=1.0,
        )


def test_benchmark_core_does_not_modify_formal_database_or_parquet(tmp_path) -> None:
    before = integrity_snapshot()
    config = BenchmarkConfig(
        query_types=[QueryType.SUM],
        trials=2,
        epsilons=[1.0],
        window_caps=[20.0],
        party_counts=[1],
        household_counts=[2],
        seed=2026,
        output_dir=tmp_path,
    )
    BenchmarkRunner(config, FakeExperimentData()).run()
    after = integrity_snapshot()
    assert after["database"] == before["database"]
    assert after["parquet"] == before["parquet"]
