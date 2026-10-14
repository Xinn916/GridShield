from pathlib import Path

from scripts.run_performance_benchmark import (
    BENCHMARK_ID,
    PARTIES,
    build_experiment_matrix,
    execute_once,
    summarize,
)


class CompletedClient:
    def __init__(self, response=None):
        self.response = response or {
            "id": "PERF-test-001",
            "status": "COMPLETED",
            "summary": {
                "total_duration_ms": 12.5,
                "communication_bytes": 2048,
                "average_response_ms": 3.25,
                "participant_nodes": 6,
            },
        }
        self.get_calls = 0

    def start_test(self, experiment):
        return self.response

    def get_test(self, test_id):
        self.get_calls += 1
        return self.response


def test_matrix_has_all_12_combinations_and_real_payload_rules():
    matrix = build_experiment_matrix()
    assert len(matrix) == 12
    assert {(item.query_type, item.mode) for item in matrix} == {
        (query_type, mode)
        for query_type in ("SUM", "COUNT", "AVERAGE", "TIME_SERIES")
        for mode in ("PLAIN", "SECRET_SHARE", "DISTRIBUTED_DP")
    }
    for item in matrix:
        payload = item.payload()
        assert payload["benchmark_id"] == BENCHMARK_ID
        assert payload["parties"] == list(PARTIES)
        assert (payload.get("interval") == "1h") == (item.query_type == "TIME_SERIES")
        assert (payload.get("epsilon") == 1.0) == (item.mode == "DISTRIBUTED_DP")
        if item.mode != "DISTRIBUTED_DP":
            assert "epsilon" not in payload
        if item.query_type != "TIME_SERIES":
            assert "interval" not in payload


def test_execute_once_uses_total_duration_and_bytes_to_kb():
    row = execute_once(CompletedClient(), build_experiment_matrix()[0], 1, 0, 1)
    assert row["status"] == "COMPLETED"
    assert row["duration_ms"] == "12.5"
    assert row["communication_bytes"] == 2048
    assert row["communication_kb"] == "2"
    assert row["test_id"] == "PERF-test-001"


def test_running_response_is_polled_until_completed():
    client = CompletedClient()
    client.response = {
        "id": "PERF-running-001",
        "status": "RUNNING",
    }

    def complete_after_poll(test_id):
        client.get_calls += 1
        return {
            "id": test_id,
            "status": "COMPLETED",
            "summary": {"total_duration_ms": 5, "communication_bytes": 1024},
        }

    client.get_test = complete_after_poll
    row = execute_once(client, build_experiment_matrix()[0], 1, 0, 1)
    assert row["status"] == "COMPLETED"
    assert client.get_calls == 1


def test_failed_rows_do_not_pollute_success_summary():
    experiment = build_experiment_matrix()[0]
    successful = execute_once(CompletedClient(), experiment, 1, 0, 1)
    failed = execute_once(
        CompletedClient({"id": "PERF-failed-001", "status": "FAILED", "error": "upstream unavailable"}),
        experiment,
        1,
        0,
        2,
    )
    summary = summarize(experiment, [successful, failed])
    assert failed["status"] == "FAILED"
    assert summary["samples"] == 1
    assert summary["duration_mean_ms"] == "12.5"
    assert summary["communication_mean_kb"] == "2"


def test_summary_uses_population_stddev():
    experiment = build_experiment_matrix()[0]
    rows = [
        {"status": "COMPLETED", "duration_ms": "10", "communication_kb": "1"},
        {"status": "COMPLETED", "duration_ms": "20", "communication_kb": "3"},
    ]
    summary = summarize(experiment, rows)
    assert summary["duration_mean_ms"] == "15"
    assert summary["duration_std_ms"] == "5"
    assert summary["communication_mean_kb"] == "2"
    assert summary["communication_std_kb"] == "1"


def test_script_uses_hidden_password_input_and_has_no_password_literal():
    source = Path(__file__).with_name("run_performance_benchmark.py").read_text(encoding="utf-8")
    assert "getpass.getpass" in source
    assert "analyst-demo" not in source
    assert "owner-a-demo" not in source
    assert "DEMO_ADMIN_PASSWORD" not in source
