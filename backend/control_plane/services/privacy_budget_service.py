from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from common.schemas import PrivacyBudgetResponse
from control_plane.models.privacy_budget import PrivacyBudget
from control_plane.models.privacy_reservation import PrivacyReservation


class PrivacyBudgetError(RuntimeError):
    pass


class InsufficientPrivacyBudgetError(PrivacyBudgetError):
    pass


@dataclass(frozen=True)
class BudgetOperation:
    status: str
    budget_before: float
    budget_after: float | None


class PrivacyBudgetService:
    def __init__(self, session: Session, default_total_epsilon: float = 20.0):
        self.session = session
        self.default_total_epsilon = default_total_epsilon

    def get_or_create(self, subject_id: str, data_scope: str) -> PrivacyBudget:
        budget = self.session.scalar(
            select(PrivacyBudget).where(
                PrivacyBudget.subject_id == subject_id,
                PrivacyBudget.data_scope == data_scope,
            )
        )
        if budget is None:
            budget = PrivacyBudget(
                budget_id=f"BUDGET-{subject_id}-{data_scope}",
                subject_id=subject_id,
                data_scope=data_scope,
                total_epsilon=self.default_total_epsilon,
                used_epsilon=0.0,
                reserved_epsilon=0.0,
            )
            self.session.add(budget)
            try:
                self.session.commit()
            except IntegrityError:
                # Another transaction may create the same unique
                # (subject_id, data_scope) row first on PostgreSQL.
                self.session.rollback()
                budget = self.session.scalar(
                    select(PrivacyBudget).where(
                        PrivacyBudget.subject_id == subject_id,
                        PrivacyBudget.data_scope == data_scope,
                    )
                )
                if budget is None:
                    raise
        return budget

    def reserve(self, task_id: str, subject_id: str, data_scope: str, epsilon: float) -> BudgetOperation:
        existing = self.session.get(PrivacyReservation, task_id)
        if existing is not None:
            if existing.epsilon != epsilon or existing.budget_id != f"BUDGET-{subject_id}-{data_scope}":
                raise PrivacyBudgetError("task_id already has a different budget reservation")
            return BudgetOperation(existing.status, existing.budget_before, existing.budget_after)

        budget = self.get_or_create(subject_id, data_scope)
        available = budget.total_epsilon - budget.used_epsilon - budget.reserved_epsilon
        result = self.session.execute(
            update(PrivacyBudget)
            .where(
                PrivacyBudget.budget_id == budget.budget_id,
                PrivacyBudget.total_epsilon
                - PrivacyBudget.used_epsilon
                - PrivacyBudget.reserved_epsilon
                >= epsilon,
            )
            .values(reserved_epsilon=PrivacyBudget.reserved_epsilon + epsilon)
        )
        if result.rowcount != 1:
            self.session.rollback()
            raise InsufficientPrivacyBudgetError("insufficient privacy budget")
        self.session.add(
            PrivacyReservation(
                task_id=task_id,
                budget_id=budget.budget_id,
                epsilon=epsilon,
                status="RESERVED",
                budget_before=available,
            )
        )
        self.session.commit()
        return BudgetOperation("RESERVED", available, None)

    def consume(self, task_id: str) -> BudgetOperation:
        reservation = self._reservation(task_id)
        if reservation.status == "CONSUMED":
            return BudgetOperation(reservation.status, reservation.budget_before, reservation.budget_after)
        if reservation.status != "RESERVED":
            raise PrivacyBudgetError(f"cannot consume a {reservation.status} reservation")
        transition = self.session.execute(
            update(PrivacyReservation)
            .where(
                PrivacyReservation.task_id == task_id,
                PrivacyReservation.status == "RESERVED",
            )
            .values(status="CONSUMED")
        )
        if transition.rowcount != 1:
            self.session.rollback()
            current = self._reservation(task_id)
            if current.status == "CONSUMED":
                return BudgetOperation(current.status, current.budget_before, current.budget_after)
            raise PrivacyBudgetError(f"cannot consume a {current.status} reservation")
        self.session.execute(
            update(PrivacyBudget)
            .where(PrivacyBudget.budget_id == reservation.budget_id)
            .values(
                reserved_epsilon=PrivacyBudget.reserved_epsilon - reservation.epsilon,
                used_epsilon=PrivacyBudget.used_epsilon + reservation.epsilon,
            )
        )
        budget = self.session.get(PrivacyBudget, reservation.budget_id)
        self.session.flush()
        self.session.refresh(budget)
        budget_after = budget.total_epsilon - budget.used_epsilon - budget.reserved_epsilon
        self.session.execute(
            update(PrivacyReservation)
            .where(PrivacyReservation.task_id == task_id)
            .values(budget_after=budget_after)
        )
        self.session.commit()
        return BudgetOperation("CONSUMED", reservation.budget_before, budget_after)

    def release(self, task_id: str) -> BudgetOperation:
        reservation = self._reservation(task_id)
        if reservation.status == "RELEASED":
            return BudgetOperation(reservation.status, reservation.budget_before, reservation.budget_after)
        if reservation.status == "CONSUMED":
            return BudgetOperation(reservation.status, reservation.budget_before, reservation.budget_after)
        transition = self.session.execute(
            update(PrivacyReservation)
            .where(
                PrivacyReservation.task_id == task_id,
                PrivacyReservation.status == "RESERVED",
            )
            .values(status="RELEASED")
        )
        if transition.rowcount != 1:
            self.session.rollback()
            current = self._reservation(task_id)
            return BudgetOperation(current.status, current.budget_before, current.budget_after)
        self.session.execute(
            update(PrivacyBudget)
            .where(PrivacyBudget.budget_id == reservation.budget_id)
            .values(reserved_epsilon=PrivacyBudget.reserved_epsilon - reservation.epsilon)
        )
        budget = self.session.get(PrivacyBudget, reservation.budget_id)
        self.session.flush()
        self.session.refresh(budget)
        budget_after = budget.total_epsilon - budget.used_epsilon - budget.reserved_epsilon
        self.session.execute(
            update(PrivacyReservation)
            .where(PrivacyReservation.task_id == task_id)
            .values(budget_after=budget_after)
        )
        self.session.commit()
        return BudgetOperation("RELEASED", reservation.budget_before, budget_after)

    def response(self, subject_id: str, data_scope: str) -> PrivacyBudgetResponse:
        budget = self.get_or_create(subject_id, data_scope)
        return PrivacyBudgetResponse(
            budget_id=budget.budget_id,
            subject_id=budget.subject_id,
            data_scope=budget.data_scope,
            total_epsilon=budget.total_epsilon,
            used_epsilon=budget.used_epsilon,
            reserved_epsilon=budget.reserved_epsilon,
            remaining_epsilon=budget.total_epsilon - budget.used_epsilon - budget.reserved_epsilon,
            created_at=budget.created_at,
            updated_at=budget.updated_at,
        )

    def _reservation(self, task_id: str) -> PrivacyReservation:
        reservation = self.session.get(PrivacyReservation, task_id)
        if reservation is None:
            raise PrivacyBudgetError("privacy budget reservation not found")
        return reservation
