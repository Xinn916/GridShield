"""Reset the local demo privacy budget.

This script is intentionally CLI-only and is not suitable for production use.
It changes only the selected demo budget row; tasks, audits, and reservations
are never deleted.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, inspect, select


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from common.schemas import utc_now  # noqa: E402
from control_plane.config import ControlSettings  # noqa: E402
from control_plane.database.session import create_session_factory, create_tables  # noqa: E402
from control_plane.models.privacy_budget import PrivacyBudget  # noqa: E402
from control_plane.models.privacy_reservation import PrivacyReservation  # noqa: E402


DEFAULT_SUBJECT_ID = "demo-analyst"
DEFAULT_DATA_SCOPE = "GLOBAL"


@dataclass(frozen=True)
class BudgetSnapshot:
    total_epsilon: float
    used_epsilon: float
    reserved_epsilon: float

    @property
    def remaining_epsilon(self) -> float:
        return self.total_epsilon - self.used_epsilon - self.reserved_epsilon


def snapshot(budget: PrivacyBudget | None) -> BudgetSnapshot:
    if budget is None:
        return BudgetSnapshot(0.0, 0.0, 0.0)
    return BudgetSnapshot(
        float(budget.total_epsilon),
        float(budget.used_epsilon),
        float(budget.reserved_epsilon),
    )


def print_snapshot(label: str, value: BudgetSnapshot) -> None:
    print(label)
    print(f"  total_epsilon: {value.total_epsilon:g}")
    print(f"  used_epsilon: {value.used_epsilon:g}")
    print(f"  reserved_epsilon: {value.reserved_epsilon:g}")
    print(f"  remaining_epsilon: {value.remaining_epsilon:g}")


def database_url() -> str:
    return os.getenv("DATABASE_URL", ControlSettings.database_url)


def reset_budget(
    session,
    *,
    subject_id: str = DEFAULT_SUBJECT_ID,
    data_scope: str = DEFAULT_DATA_SCOPE,
    total_epsilon: float = 20.0,
) -> tuple[BudgetSnapshot, BudgetSnapshot, int]:
    """Reset one budget row in the caller's active transaction."""
    budget = session.scalar(
        select(PrivacyBudget)
        .where(
            PrivacyBudget.subject_id == subject_id,
            PrivacyBudget.data_scope == data_scope,
        )
        .with_for_update()
    )
    before = snapshot(budget)
    if budget is None:
        budget = PrivacyBudget(
            budget_id=f"BUDGET-{subject_id}-{data_scope}",
            subject_id=subject_id,
            data_scope=data_scope,
            total_epsilon=total_epsilon,
            used_epsilon=0.0,
            reserved_epsilon=0.0,
        )
        session.add(budget)
    else:
        budget.total_epsilon = total_epsilon
        budget.used_epsilon = 0.0
        budget.reserved_epsilon = 0.0
        budget.updated_at = utc_now()
    session.flush()
    active_count = session.scalar(
        select(func.count())
        .where(
            PrivacyReservation.budget_id == budget.budget_id,
            PrivacyReservation.status == "RESERVED",
        )
        .with_for_update()
    )
    return before, snapshot(budget), int(active_count or 0)


def parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        description=(
            "LOCAL DEVELOPMENT ONLY: preview or reset the demo privacy budget. "
            "Never use this command against a production database."
        ),
        epilog="WARNING: this is a local demo operation, not a production control.",
    )


def main(argv: list[str] | None = None) -> int:
    arguments = parser()
    arguments.add_argument("--total-epsilon", type=float, default=20.0)
    arguments.add_argument(
        "--confirm",
        action="store_true",
        help="commit the reset; without this flag the command is read-only",
    )
    args = arguments.parse_args(argv)
    if args.total_epsilon <= 0:
        arguments.error("--total-epsilon must be positive")

    print("WARNING: reset_demo_budget.py is for local development/demo only; never use it in production.")
    factory = create_session_factory(database_url())
    engine = factory.kw["bind"]
    if not inspect(engine).has_table("privacy_budgets"):
        if not args.confirm:
            print("No privacy budget table exists; preview made no changes.")
            return 0
        create_tables(factory)

    with factory() as session:
        if args.confirm:
            current = session.scalar(
                select(PrivacyBudget).where(
                    PrivacyBudget.subject_id == DEFAULT_SUBJECT_ID,
                    PrivacyBudget.data_scope == DEFAULT_DATA_SCOPE,
                )
            )
            displayed_before = snapshot(current)
            print_snapshot("Current budget before reset:", displayed_before)
            session.rollback()
            with session.begin():
                before, after, active_count = reset_budget(
                    session, total_epsilon=args.total_epsilon
                )
            # The transaction re-reads the row under its lock; keep this assertion
            # to make the displayed pre-reset values auditable during development.
            if before != displayed_before:
                raise RuntimeError("budget changed before reset transaction completed")
            if active_count:
                print(
                    "WARNING: active reservations were not deleted; "
                    "finish or release them before running production-like tasks."
                )
            print_snapshot("Budget after reset:", after)
            print("Reset committed. Task and audit records were preserved.")
        else:
            budget = session.scalar(
                select(PrivacyBudget).where(
                    PrivacyBudget.subject_id == DEFAULT_SUBJECT_ID,
                    PrivacyBudget.data_scope == DEFAULT_DATA_SCOPE,
                )
            )
            print_snapshot("Current budget (preview only):", snapshot(budget))
            print(
                f"Planned reset: total_epsilon={args.total_epsilon:g}, "
                "used_epsilon=0, reserved_epsilon=0, "
                f"remaining_epsilon={args.total_epsilon:g}"
            )
            print("No changes made. Re-run with --confirm to commit this local demo reset.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
