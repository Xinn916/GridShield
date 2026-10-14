import hashlib
import json
from datetime import datetime, timedelta

import duckdb

from conftest import PROJECT_DIR


DATA_DIR = PROJECT_DIR / "data_processed"
SUMMARY_PATH = DATA_DIR / "sample_summary.json"
FILES = {
    "ORG_A": DATA_DIR / "party_a.parquet",
    "ORG_B": DATA_DIR / "party_b.parquet",
    "ORG_C": DATA_DIR / "party_c.parquet",
}
EXPECTED_COLUMNS = ["household_id", "organization_id", "timestamp", "energy_kwh"]


def sha256(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def id_digest(ids) -> str:
    return hashlib.sha256("\n".join(sorted(ids)).encode("utf-8")).hexdigest()


def test_sample_summary_matches_existing_parquet_files() -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    connection = duckdb.connect(":memory:")
    household_sets = {}
    total_records = 0
    total_energy = 0.0

    assert summary["schema"] == EXPECTED_COLUMNS
    for organization, path in FILES.items():
        actual = connection.execute(
            """SELECT count(DISTINCT household_id), count(*), min(timestamp), max(timestamp),
                      sum(energy_kwh), min(organization_id), max(organization_id)
               FROM read_parquet(?)""",
            [str(path)],
        ).fetchone()
        ids = {
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT household_id FROM read_parquet(?)", [str(path)]
            ).fetchall()
        }
        household_sets[organization] = ids
        party = summary["parties"][organization]
        assert party["household_count"] == actual[0]
        assert party["record_count"] == actual[1]
        assert party["start_time"] == actual[2].isoformat()
        assert party["end_time"] == actual[3].isoformat()
        assert party["energy_sum"] == actual[4]
        assert party["household_ids_sha256"] == id_digest(ids)
        assert actual[5] == actual[6] == organization
        total_records += actual[1]
        total_energy += actual[4]

    assert household_sets["ORG_A"].isdisjoint(household_sets["ORG_B"])
    assert household_sets["ORG_A"].isdisjoint(household_sets["ORG_C"])
    assert household_sets["ORG_B"].isdisjoint(household_sets["ORG_C"])
    assert summary["households_mutually_exclusive"] is True
    assert summary["global"]["household_count"] == len(set().union(*household_sets.values()))
    assert summary["global"]["record_count"] == total_records
    assert summary["global"]["energy_sum"] == total_energy


def test_sample_summary_window_and_source_hashes_are_consistent() -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    window = summary["continuous_window"]
    start = datetime.fromisoformat(window["start_time"])
    end_exclusive = datetime.fromisoformat(window["end_time_exclusive"])
    observed_end = datetime.fromisoformat(window["last_observation_time"])
    interval = timedelta(minutes=window["interval_minutes"])
    assert end_exclusive == observed_end + interval
    assert (end_exclusive - start).total_seconds() / 86_400 == window["days"]
    assert window["is_complete"] is True
    assert window["minimum_records_per_household"] == window["expected_records_per_household"]
    assert window["maximum_records_per_household"] == window["expected_records_per_household"]

    integrity = summary["source_integrity"]
    assert integrity["algorithm"] == "SHA-256"
    assert integrity["unchanged"] is True
    for organization, path in FILES.items():
        actual_hash = sha256(path)
        assert integrity["before"][organization] == actual_hash
        assert integrity["after"][organization] == actual_hash
