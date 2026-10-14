import duckdb
import pandas as pd
import pyarrow.parquet as pq

from conftest import PROJECT_DIR


PREVIEW_FILES = [
    PROJECT_DIR / "data_processed" / "preview_snappy" / "party_a.parquet",
    PROJECT_DIR / "data_processed" / "preview_snappy" / "party_b.parquet",
    PROJECT_DIR / "data_processed" / "preview_snappy" / "party_c.parquet",
]
EXPECTED_COLUMNS = ["household_id", "organization_id", "timestamp", "energy_kwh"]


def test_preview_files_are_snappy_and_readable_by_pandas() -> None:
    for file in PREVIEW_FILES:
        frame = pd.read_parquet(file)
        assert frame.columns.tolist() == EXPECTED_COLUMNS
        assert frame["household_id"].nunique() == 100
        metadata = pq.ParquetFile(file).metadata
        codecs = {
            metadata.row_group(group).column(column).compression
            for group in range(metadata.num_row_groups)
            for column in range(metadata.row_group(group).num_columns)
        }
        assert codecs == {"SNAPPY"}


def test_preview_files_are_readable_by_duckdb_and_households_do_not_overlap() -> None:
    connection = duckdb.connect(":memory:")
    household_sets = []
    for file in PREVIEW_FILES:
        columns = [
            row[0]
            for row in connection.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)", [str(file)]
            ).fetchall()
        ]
        assert columns == EXPECTED_COLUMNS
        households = {
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT household_id FROM read_parquet(?)", [str(file)]
            ).fetchall()
        }
        assert len(households) == 100
        household_sets.append(households)
    assert household_sets[0].isdisjoint(household_sets[1])
    assert household_sets[0].isdisjoint(household_sets[2])
    assert household_sets[1].isdisjoint(household_sets[2])
