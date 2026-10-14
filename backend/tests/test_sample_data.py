import duckdb

from conftest import PROJECT_DIR


FILES = [
    PROJECT_DIR / "data_processed" / "party_a.parquet",
    PROJECT_DIR / "data_processed" / "party_b.parquet",
    PROJECT_DIR / "data_processed" / "party_c.parquet",
]


def test_each_party_has_exactly_100_households() -> None:
    connection = duckdb.connect(":memory:")
    for file in FILES:
        count = connection.execute("SELECT count(DISTINCT household_id) FROM read_parquet(?)", [str(file)]).fetchone()[0]
        assert count == 100


def test_households_do_not_overlap_between_parties() -> None:
    connection = duckdb.connect(":memory:")
    sets = [
        {row[0] for row in connection.execute("SELECT DISTINCT household_id FROM read_parquet(?)", [str(file)]).fetchall()}
        for file in FILES
    ]
    assert sets[0].isdisjoint(sets[1])
    assert sets[0].isdisjoint(sets[2])
    assert sets[1].isdisjoint(sets[2])


def test_sample_window_is_continuous_30_days() -> None:
    connection = duckdb.connect(":memory:")
    for file in FILES:
        records, minimum, maximum = connection.execute(
            "SELECT count(*), min(timestamp), max(timestamp) FROM read_parquet(?)", [str(file)]
        ).fetchone()
        assert records == 100 * 30 * 48
        assert (maximum - minimum).total_seconds() == (30 * 48 - 1) * 30 * 60
