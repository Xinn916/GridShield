import logging
from dataclasses import dataclass, field
from threading import RLock

from common.enums import ComputeTaskStatus, QueryType
from common.schemas import (
    ComputeTaskRegistration,
    ShareAggregateResponse,
    ShareReceipt,
    ShareSubmission,
)
from compute_node.aggregator import aggregate_submissions


logger = logging.getLogger(__name__)


class ShareStoreError(ValueError):
    pass


@dataclass
class TaskShares:
    registration: ComputeTaskRegistration
    submissions: dict = field(default_factory=dict)
    scale: int | None = None
    count_scale: int = 1
    status: ComputeTaskStatus = ComputeTaskStatus.WAITING
    error: str | None = None
    bucket_timestamps: list | None = None


class ShareStore:
    def __init__(self, node_id: str, share_index: int):
        self.node_id = node_id
        self.share_index = share_index
        self._tasks: dict[str, TaskShares] = {}
        self._lock = RLock()

    def register(self, registration: ComputeTaskRegistration) -> ShareAggregateResponse:
        with self._lock:
            state = self._tasks.get(registration.task_id)
            if state is None:
                state = TaskShares(registration=registration)
                self._tasks[registration.task_id] = state
            elif state.registration != registration:
                raise ShareStoreError("task_id is already registered with different parameters")
            return self._response(registration.task_id, state)

    def submit(self, submission: ShareSubmission) -> ShareReceipt:
        with self._lock:
            if submission.share_index != self.share_index:
                raise ShareStoreError(
                    f"{self.node_id} only accepts share_index={self.share_index}"
                )
            state = self._tasks.get(submission.task_id)
            if state is None:
                raise ShareStoreError("task must be registered before shares are submitted")
            expected = state.registration.expected_parties
            if submission.party_id not in expected:
                raise ShareStoreError("unexpected party_id")
            if submission.expected_parties != expected:
                raise ShareStoreError("expected_parties does not match task registration")
            if submission.query_type != state.registration.query_type:
                raise ShareStoreError("query_type does not match task registration")
            if state.status == ComputeTaskStatus.FAILED:
                raise ShareStoreError(state.error or "task aggregation failed")
            if submission.query_type == QueryType.TIME_SERIES:
                self._validate_time_series(submission, state)
            if state.scale is not None and submission.scale != state.scale:
                raise ShareStoreError("scale does not match previous submissions")
            if state.submissions and submission.count_scale != state.count_scale:
                raise ShareStoreError("count_scale does not match previous submissions")

            existing = state.submissions.get(submission.party_id)
            if existing is not None:
                if existing != submission:
                    raise ShareStoreError("party_id already submitted a different share")
                return self._receipt(submission, state, idempotent=True)

            state.scale = submission.scale
            state.count_scale = submission.count_scale
            state.submissions[submission.party_id] = submission
            if len(state.submissions) == len(expected):
                state.status = ComputeTaskStatus.READY
                logger.info("%s %s aggregate ready", submission.task_id, self.node_id)
            else:
                logger.info(
                    "%s %s waiting %d/%d",
                    submission.task_id,
                    self.node_id,
                    len(state.submissions),
                    len(expected),
                )
            return self._receipt(submission, state)

    def _validate_time_series(self, submission: ShareSubmission, state: TaskShares) -> None:
        registration = state.registration
        buckets = submission.payload.buckets or []
        timestamps = [item.timestamp for item in buckets]
        error = None
        if submission.bucket_count != len(buckets):
            error = "bucket_count does not match payload"
        elif timestamps != sorted(timestamps):
            error = "bucket timestamps must be in ascending order"
        elif registration.group_by is not None and submission.group_by != registration.group_by:
            error = "group_by does not match task registration"
        elif registration.bucket_count is not None and submission.bucket_count != registration.bucket_count:
            error = "bucket_count does not match task registration"
        elif state.bucket_timestamps is not None and timestamps != state.bucket_timestamps:
            error = "time-series bucket timestamps do not match previous submissions"
        if error is not None:
            state.status = ComputeTaskStatus.FAILED
            state.error = error
            logger.warning("%s %s time-series validation failed: %s", submission.task_id, self.node_id, error)
            raise ShareStoreError(error)
        if state.bucket_timestamps is None:
            state.bucket_timestamps = timestamps

    def aggregate(self, task_id: str) -> ShareAggregateResponse:
        with self._lock:
            state = self._tasks.get(task_id)
            if state is None:
                raise KeyError(task_id)
            return self._response(task_id, state)

    def _response(self, task_id: str, state: TaskShares) -> ShareAggregateResponse:
        payload = None
        if state.status == ComputeTaskStatus.READY:
            payload = aggregate_submissions(
                state.registration.query_type, list(state.submissions.values())
            )
        return ShareAggregateResponse(
            task_id=task_id,
            share_index=self.share_index,
            query_type=state.registration.query_type,
            status=state.status,
            scale=state.scale,
            count_scale=state.count_scale,
            received_parties=len(state.submissions),
            expected_parties=len(state.registration.expected_parties),
            payload=payload,
            error=state.error,
        )

    def _receipt(
        self, submission: ShareSubmission, state: TaskShares, idempotent: bool = False
    ) -> ShareReceipt:
        return ShareReceipt(
            task_id=submission.task_id,
            party_id=submission.party_id,
            share_index=self.share_index,
            status=state.status,
            received_parties=len(state.submissions),
            expected_parties=len(state.registration.expected_parties),
            idempotent=idempotent,
        )
