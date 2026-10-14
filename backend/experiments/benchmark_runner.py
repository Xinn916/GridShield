from __future__ import annotations

import math
import statistics
import time
import tracemalloc

from common.enums import OrganizationId, QueryType
from common.fixed_point import SCALE, decode, encode
from common.secret_sharing import PRIME
from experiments.data import ExperimentData
from experiments.models import BenchmarkConfig, ExperimentMode, PreparedStatistics, TrialResult
from experiments.primitives import ExperimentRandom, reconstruct, serialized_size


def sensitivity_for(query_type: QueryType, prepared: PreparedStatistics) -> float:
    return 1.0 if query_type == QueryType.COUNT else prepared.window_cap


def percentile95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


class TrialExecutor:
    def __init__(self, rng: ExperimentRandom, minimum_denominator: float = 10.0):
        self.rng = rng
        self.minimum_denominator = minimum_denominator

    def execute(
        self,
        prepared: PreparedStatistics,
        query_type: QueryType,
        mode: ExperimentMode,
        epsilon: float,
    ) -> TrialResult:
        tracemalloc.start()
        started = time.perf_counter()
        noise_ms = 0.0
        sharing_ms = 0.0
        aggregation_ms = 0.0
        party_s1 = party_s2 = compute_control = direct_control = 0

        if mode == ExperimentMode.PLAIN:
            aggregate_started = time.perf_counter()
            value = prepared.true_value(query_type)
            aggregation_ms = (time.perf_counter() - aggregate_started) * 1000
            direct_control = sum(
                serialized_size(self._local_payload(query_type, prepared.local_sums[p], prepared.local_counts[p]))
                for p in prepared.parties
            )
        elif mode == ExperimentMode.CENTRAL_DP:
            direct_control = sum(
                serialized_size(self._local_payload(query_type, prepared.local_sums[p], prepared.local_counts[p]))
                for p in prepared.parties
            )
            noise_started = time.perf_counter()
            value = self._central_dp(prepared, query_type, epsilon)
            noise_ms = (time.perf_counter() - noise_started) * 1000
        elif mode == ExperimentMode.LOCAL_DP:
            noise_started = time.perf_counter()
            noisy = [
                self._noisy_local(
                    query_type,
                    prepared.local_sums[party],
                    prepared.local_counts[party],
                    prepared.window_cap,
                    epsilon,
                    participants=1,
                )
                for party in prepared.parties
            ]
            noise_ms = (time.perf_counter() - noise_started) * 1000
            aggregate_started = time.perf_counter()
            value = self._combine_noisy(query_type, noisy)
            aggregation_ms = (time.perf_counter() - aggregate_started) * 1000
            direct_control = sum(serialized_size(self._tuple_payload(query_type, item)) for item in noisy)
        else:
            distributed = mode == ExperimentMode.DISTRIBUTED_DP
            noisy_values = []
            noise_started = time.perf_counter()
            for party in prepared.parties:
                if distributed:
                    noisy_values.append(
                        self._noisy_local(
                            query_type,
                            prepared.local_sums[party],
                            prepared.local_counts[party],
                            prepared.window_cap,
                            epsilon,
                            participants=len(prepared.parties),
                        )
                    )
                else:
                    noisy_values.append((prepared.local_sums[party], float(prepared.local_counts[party])))
            noise_ms = (time.perf_counter() - noise_started) * 1000 if distributed else 0.0

            share_started = time.perf_counter()
            node_1 = []
            node_2 = []
            for party, item in zip(prepared.parties, noisy_values):
                encoded = self._encode_tuple(query_type, item, distributed)
                first_payload = []
                second_payload = []
                for value_item in encoded:
                    first, second = self.rng.split_secret(value_item)
                    first_payload.append(first)
                    second_payload.append(second)
                node_1.append(first_payload)
                node_2.append(second_payload)
                party_s1 += serialized_size(
                    {"party_id": party.value, "share_index": 1, "payload": first_payload}
                )
                party_s2 += serialized_size(
                    {"party_id": party.value, "share_index": 2, "payload": second_payload}
                )
            sharing_ms = (time.perf_counter() - share_started) * 1000

            aggregate_started = time.perf_counter()
            aggregate_1 = [sum(values[index] for values in node_1) % PRIME for index in range(len(node_1[0]))]
            aggregate_2 = [sum(values[index] for values in node_2) % PRIME for index in range(len(node_2[0]))]
            reconstructed = [reconstruct(first, second) for first, second in zip(aggregate_1, aggregate_2)]
            value = self._decode_aggregate(query_type, reconstructed, distributed)
            aggregation_ms = (time.perf_counter() - aggregate_started) * 1000
            compute_control = serialized_size({"share_index": 1, "payload": aggregate_1}) + serialized_size(
                {"share_index": 2, "payload": aggregate_2}
            )

        algorithm_ms = (time.perf_counter() - started) * 1000
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return TrialResult(
            value=value,
            execution_time_ms=prepared.local_query_time_ms + algorithm_ms,
            local_query_time_ms=prepared.local_query_time_ms,
            clipping_time_ms=prepared.clipping_time_ms,
            noise_time_ms=noise_ms,
            secret_sharing_time_ms=sharing_ms,
            aggregation_time_ms=aggregation_ms,
            peak_memory_kb=max(prepared.peak_memory_kb, peak / 1024),
            party_to_s1_bytes=party_s1,
            party_to_s2_bytes=party_s2,
            compute_to_control_bytes=compute_control,
            direct_to_control_bytes=direct_control,
        )

    def _central_dp(self, prepared, query_type, epsilon):
        total_sum = sum(prepared.local_sums.values())
        total_count = float(sum(prepared.local_counts.values()))
        if query_type == QueryType.SUM:
            return total_sum + self.rng.gamma_difference(prepared.window_cap, epsilon)
        if query_type == QueryType.COUNT:
            return max(0.0, total_count + self.rng.gamma_difference(1.0, epsilon))
        noisy_sum = total_sum + self.rng.gamma_difference(prepared.window_cap, epsilon * 0.7)
        noisy_count = total_count + self.rng.gamma_difference(1.0, epsilon * 0.3)
        return self._protected_average(noisy_sum, noisy_count)

    def _noisy_local(self, query_type, local_sum, local_count, sensitivity, epsilon, participants):
        if query_type == QueryType.SUM:
            return local_sum + self.rng.gamma_difference(sensitivity, epsilon, participants), float(local_count)
        if query_type == QueryType.COUNT:
            return local_sum, local_count + self.rng.gamma_difference(1.0, epsilon, participants)
        noisy_sum = local_sum + self.rng.gamma_difference(sensitivity, epsilon * 0.7, participants)
        noisy_count = local_count + self.rng.gamma_difference(1.0, epsilon * 0.3, participants)
        return noisy_sum, noisy_count

    def _combine_noisy(self, query_type, values):
        total_sum = sum(item[0] for item in values)
        total_count = sum(item[1] for item in values)
        if query_type == QueryType.SUM:
            return total_sum
        if query_type == QueryType.COUNT:
            return max(0.0, total_count)
        return self._protected_average(total_sum, total_count)

    def _encode_tuple(self, query_type, item, distributed):
        if query_type == QueryType.SUM:
            return [encode(item[0])]
        if query_type == QueryType.COUNT:
            return [encode(item[1]) if distributed else int(item[1])]
        return [encode(item[0]), encode(item[1]) if distributed else int(item[1])]

    def _decode_aggregate(self, query_type, values, distributed):
        if query_type == QueryType.SUM:
            return decode(values[0])
        if query_type == QueryType.COUNT:
            return max(0.0, decode(values[0]) if distributed else float(values[0]))
        total_sum = decode(values[0])
        total_count = decode(values[1]) if distributed else float(values[1])
        return self._protected_average(total_sum, total_count)

    def _protected_average(self, total_sum, total_count):
        if total_count <= 0 or total_count < self.minimum_denominator:
            return None
        return total_sum / max(total_count, self.minimum_denominator)

    @staticmethod
    def _local_payload(query_type, local_sum, local_count):
        if query_type == QueryType.SUM:
            return {"value": local_sum}
        if query_type == QueryType.COUNT:
            return {"value": local_count}
        return {"sum": local_sum, "count": local_count}

    @staticmethod
    def _tuple_payload(query_type, item):
        if query_type == QueryType.SUM:
            return {"value": item[0]}
        if query_type == QueryType.COUNT:
            return {"value": item[1]}
        return {"sum": item[0], "count": item[1]}


def summarize_trials(
    trials: list[TrialResult],
    true_value: float,
    query_type: QueryType,
    mode: ExperimentMode,
    epsilon: float,
) -> dict:
    values = [trial.value for trial in trials if trial.value is not None]
    if not values:
        mean = bias = mae = rmse = relative = stddev = None
    else:
        mean = statistics.fmean(values)
        errors = [value - true_value for value in values]
        bias = statistics.fmean(errors)
        mae = statistics.fmean(abs(error) for error in errors)
        rmse = math.sqrt(statistics.fmean(error * error for error in errors))
        relative = statistics.fmean(abs(error) / abs(true_value) for error in errors) if true_value else None
        stddev = statistics.stdev(values) if len(values) > 1 else 0.0
    row = {
        "query_type": query_type.value,
        "method": mode.value,
        "epsilon": epsilon,
        "trials": len(trials),
        "protected_runs": len(trials) - len(values),
        "true_value": true_value,
        "mean_private_value": mean,
        "bias": bias,
        "mae": mae,
        "rmse": rmse,
        "mean_relative_error": relative,
        "sample_standard_deviation": stddev,
        "average_execution_time_ms": statistics.fmean(t.execution_time_ms for t in trials),
        "p95_execution_time_ms": percentile95([t.execution_time_ms for t in trials]),
        "average_local_query_time_ms": statistics.fmean(t.local_query_time_ms for t in trials),
        "average_clipping_time_ms": statistics.fmean(t.clipping_time_ms for t in trials),
        "average_noise_time_ms": statistics.fmean(t.noise_time_ms for t in trials),
        "average_secret_sharing_time_ms": statistics.fmean(t.secret_sharing_time_ms for t in trials),
        "average_aggregation_time_ms": statistics.fmean(t.aggregation_time_ms for t in trials),
        "peak_memory_kb": max(t.peak_memory_kb for t in trials),
        "party_to_s1_bytes": statistics.fmean(t.party_to_s1_bytes for t in trials),
        "party_to_s2_bytes": statistics.fmean(t.party_to_s2_bytes for t in trials),
        "compute_to_control_bytes": statistics.fmean(t.compute_to_control_bytes for t in trials),
        "direct_to_control_bytes": statistics.fmean(t.direct_to_control_bytes for t in trials),
        "total_communication_bytes": statistics.fmean(t.total_communication_bytes for t in trials),
    }
    return row


class BenchmarkRunner:
    def __init__(self, config: BenchmarkConfig, data: ExperimentData | None = None):
        self.config = config
        self.data = data or ExperimentData()
        self.rng = ExperimentRandom(config.seed)
        self.executor = TrialExecutor(self.rng, config.minimum_denominator)

    def _trials(self, prepared, query_type, mode, epsilon):
        return [
            self.executor.execute(prepared, query_type, mode, epsilon)
            for _ in range(self.config.trials)
        ]

    def run(self) -> dict[str, list[dict]]:
        all_parties = list(OrganizationId)
        base = self.data.prepare(
            all_parties,
            self.config.start_time,
            self.config.end_time,
            240.0,
        )
        epsilon_rows = []
        for query_type in self.config.query_types:
            true_value = base.true_value(query_type)
            for epsilon in self.config.epsilons:
                for mode in ExperimentMode:
                    trials = self._trials(base, query_type, mode, epsilon)
                    epsilon_rows.append(summarize_trials(trials, true_value, query_type, mode, epsilon))

        reference_epsilon = min(self.config.epsilons, key=lambda value: abs(value - 1.0))
        method_rows = [row.copy() for row in epsilon_rows if row["epsilon"] == reference_epsilon]

        clipping_rows = []
        for cap in self.config.window_caps:
            prepared = self.data.prepare(
                all_parties,
                self.config.start_time,
                self.config.end_time,
                cap,
            )
            for query_type in self.config.query_types:
                unclipped = prepared.true_value(query_type, clipped=False)
                clipped = prepared.true_value(query_type, clipped=True)
                trials = self._trials(prepared, query_type, ExperimentMode.DISTRIBUTED_DP, 1.0)
                private_values = [trial.value for trial in trials if trial.value is not None]
                privacy_errors = [value - clipped for value in private_values]
                total_errors = [value - unclipped for value in private_values]
                clipping_rows.append(
                    {
                        "query_type": query_type.value,
                        "window_cap": cap,
                        "trials": self.config.trials,
                        "unclipped_plain_value": unclipped,
                        "clipped_plain_value": clipped,
                        "clipping_absolute_error": abs(clipped - unclipped),
                        "clipping_relative_error": abs(clipped - unclipped) / abs(unclipped) if unclipped else None,
                        "distributed_dp_mae": statistics.fmean(abs(error) for error in privacy_errors),
                        "distributed_dp_rmse": math.sqrt(statistics.fmean(error * error for error in privacy_errors)),
                        "total_error": statistics.fmean(abs(error) for error in total_errors),
                    }
                )

        scalability_rows = []
        for party_count in self.config.party_counts:
            prepared = self.data.prepare(
                all_parties[:party_count],
                self.config.start_time,
                self.config.end_time,
                240.0,
            )
            scalability_rows.append(
                self._scalability_row("party_count", prepared, self.config.query_types[0])
            )
        for household_count in self.config.household_counts:
            prepared = self.data.prepare(
                all_parties,
                self.config.start_time,
                self.config.end_time,
                240.0,
                household_count,
            )
            scalability_rows.append(
                self._scalability_row("household_count", prepared, self.config.query_types[0])
            )

        communication_rows = [
            {
                key: row[key]
                for key in (
                    "query_type",
                    "method",
                    "epsilon",
                    "party_to_s1_bytes",
                    "party_to_s2_bytes",
                    "compute_to_control_bytes",
                    "direct_to_control_bytes",
                    "total_communication_bytes",
                )
            }
            for row in method_rows
        ]
        communication_rows.extend(
            {
                "query_type": row["query_type"],
                "method": ExperimentMode.DISTRIBUTED_DP.value,
                "epsilon": 1.0,
                "scenario": row["scenario"],
                "party_count": row["party_count"],
                "household_count": row["household_count"],
                "party_to_s1_bytes": row["party_to_s1_bytes"],
                "party_to_s2_bytes": row["party_to_s2_bytes"],
                "compute_to_control_bytes": row["compute_to_control_bytes"],
                "direct_to_control_bytes": row["direct_to_control_bytes"],
                "total_communication_bytes": row["total_communication_bytes"],
            }
            for row in scalability_rows
        )
        return {
            "epsilon_comparison": epsilon_rows,
            "method_comparison": method_rows,
            "clipping_comparison": clipping_rows,
            "scalability_comparison": scalability_rows,
            "communication_comparison": communication_rows,
        }

    def _scalability_row(self, scenario, prepared, query_type):
        trials = self._trials(prepared, query_type, ExperimentMode.DISTRIBUTED_DP, 1.0)
        summary = summarize_trials(
            trials, prepared.true_value(query_type), query_type, ExperimentMode.DISTRIBUTED_DP, 1.0
        )
        return {
            "scenario": scenario,
            "query_type": query_type.value,
            "party_count": len(prepared.parties),
            "household_count": prepared.household_count,
            "local_query_time_ms": summary["average_local_query_time_ms"],
            "clipping_time_ms": summary["average_clipping_time_ms"],
            "noise_generation_time_ms": summary["average_noise_time_ms"],
            "secret_sharing_time_ms": summary["average_secret_sharing_time_ms"],
            "aggregation_time_ms": summary["average_aggregation_time_ms"],
            "total_execution_time_ms": summary["average_execution_time_ms"],
            "p95_execution_time_ms": summary["p95_execution_time_ms"],
            "peak_memory_kb": summary["peak_memory_kb"],
            "party_to_s1_bytes": summary["party_to_s1_bytes"],
            "party_to_s2_bytes": summary["party_to_s2_bytes"],
            "compute_to_control_bytes": summary["compute_to_control_bytes"],
            "direct_to_control_bytes": summary["direct_to_control_bytes"],
            "total_communication_bytes": summary["total_communication_bytes"],
        }
