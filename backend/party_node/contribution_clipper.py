import math
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ClippingStats:
    records_before: int
    records_after: int
    clipped_records: int
    clipped_energy_kwh: float
    window_cap: float


class ContributionClipper:
    def __init__(
        self,
        record_cap: float = 5.0,
        max_records_per_household_per_day: int = 48,
        max_window_cap: float = 7_440.0,
    ):
        if record_cap <= 0 or max_records_per_household_per_day <= 0 or max_window_cap <= 0:
            raise ValueError("contribution caps must be positive")
        self.record_cap = record_cap
        self.max_records_per_household_per_day = max_records_per_household_per_day
        self.max_window_cap = max_window_cap

    def window_cap(self, start_time: datetime, end_time: datetime) -> float:
        days = max(1, math.ceil((end_time - start_time).total_seconds() / 86_400))
        calculated = self.record_cap * self.max_records_per_household_per_day * days
        return min(calculated, self.max_window_cap)

    def cte(self, window_cap: float) -> tuple[str, list[float | int]]:
        sql = """
            scoped AS (
                SELECT household_id, timestamp, energy_kwh,
                       least(greatest(energy_kwh, 0.0), ?) AS record_value,
                       row_number() OVER (
                           PARTITION BY household_id, cast(timestamp AS DATE)
                           ORDER BY timestamp
                       ) AS daily_rank
                FROM party_data
                WHERE timestamp >= ? AND timestamp < ?
            ),
            limited AS (
                SELECT * FROM scoped WHERE daily_rank <= ?
            ),
            household_totals AS (
                SELECT household_id, sum(record_value) AS household_total
                FROM limited GROUP BY household_id
            ),
            clipped AS (
                SELECT limited.household_id, limited.timestamp,
                       limited.record_value * least(
                           1.0,
                           ? / nullif(household_totals.household_total, 0.0)
                       ) AS clipped_energy_kwh,
                       limited.energy_kwh AS original_energy_kwh,
                       limited.record_value,
                       household_totals.household_total
                FROM limited JOIN household_totals USING (household_id)
            )
        """
        return sql, [self.record_cap, self.max_records_per_household_per_day, window_cap]

    @staticmethod
    def clip_time_series_vector(values: list[float], window_cap: float) -> tuple[list[float], bool]:
        """Apply one L1 contribution cap to an entire household load vector."""
        if window_cap <= 0:
            raise ValueError("window_cap must be positive")
        total = sum(abs(float(value)) for value in values)
        if total <= window_cap or total == 0:
            return [float(value) for value in values], False
        factor = window_cap / total
        clipped = [float(value) * factor for value in values]
        return clipped, True
