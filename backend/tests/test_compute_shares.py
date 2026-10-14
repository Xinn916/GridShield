from datetime import datetime, timedelta

import pytest

from common.enums import ComputeTaskStatus, GroupBy, OrganizationId, QueryType
from common.schemas import ComputeTaskRegistration, ShareBucket, SharePayload, ShareSubmission
from compute_node.share_store import ShareStore, ShareStoreError


def registration(parties=None) -> ComputeTaskRegistration:
    return ComputeTaskRegistration(
        task_id="TASK-SHARES",
        expected_parties=parties or [OrganizationId.ORG_A, OrganizationId.ORG_B, OrganizationId.ORG_C],
        query_type=QueryType.SUM,
    )


def submission(party: OrganizationId, share_index: int = 1, value: int = 10, parties=None) -> ShareSubmission:
    return ShareSubmission(
        task_id="TASK-SHARES",
        party_id=party,
        expected_parties=parties or [OrganizationId.ORG_A, OrganizationId.ORG_B, OrganizationId.ORG_C],
        query_type=QueryType.SUM,
        share_index=share_index,
        scale=1_000_000,
        payload=SharePayload(value=value),
    )


def test_duplicate_submission_is_idempotent() -> None:
    store = ShareStore("S1", 1)
    store.register(registration())
    first = store.submit(submission(OrganizationId.ORG_A))
    retry = store.submit(submission(OrganizationId.ORG_A))
    aggregate = store.aggregate("TASK-SHARES")
    assert first.received_parties == retry.received_parties == 1
    assert retry.idempotent is True
    assert aggregate.received_parties == 1


def test_unexpected_party_is_rejected() -> None:
    store = ShareStore("S1", 1)
    store.register(registration([OrganizationId.ORG_A]))
    with pytest.raises(ShareStoreError, match="unexpected party_id"):
        store.submit(
            submission(
                OrganizationId.ORG_B,
                parties=[OrganizationId.ORG_A, OrganizationId.ORG_B],
            )
        )


@pytest.mark.parametrize(
    ("node_id", "expected_index", "received_index"),
    [("S1", 1, 2), ("S2", 2, 1)],
)
def test_compute_node_rejects_wrong_share_index(node_id, expected_index, received_index) -> None:
    store = ShareStore(node_id, expected_index)
    store.register(registration())
    with pytest.raises(ShareStoreError, match=f"share_index={expected_index}"):
        store.submit(submission(OrganizationId.ORG_A, share_index=received_index))


def test_missing_party_keeps_status_waiting() -> None:
    store = ShareStore("S1", 1)
    store.register(registration())
    store.submit(submission(OrganizationId.ORG_A))
    store.submit(submission(OrganizationId.ORG_B))
    aggregate = store.aggregate("TASK-SHARES")
    assert aggregate.status == ComputeTaskStatus.WAITING
    assert aggregate.payload is None
    assert aggregate.received_parties == 2


def time_series_submission(party, timestamps, group_by=GroupBy.HOUR) -> ShareSubmission:
    return ShareSubmission(
        task_id="TASK-SERIES",
        party_id=party,
        expected_parties=[OrganizationId.ORG_A, OrganizationId.ORG_B],
        query_type=QueryType.TIME_SERIES,
        group_by=group_by,
        bucket_count=len(timestamps),
        share_index=1,
        payload=SharePayload(
            buckets=[ShareBucket(timestamp=timestamp, value=index + 1) for index, timestamp in enumerate(timestamps)]
        ),
    )


def test_compute_node_rejects_misaligned_time_series_buckets_and_marks_failed() -> None:
    start = datetime(2012, 1, 1)
    store = ShareStore("S1", 1)
    store.register(
        ComputeTaskRegistration(
            task_id="TASK-SERIES",
            expected_parties=[OrganizationId.ORG_A, OrganizationId.ORG_B],
            query_type=QueryType.TIME_SERIES,
            group_by=GroupBy.HOUR,
            bucket_count=2,
        )
    )
    store.submit(time_series_submission(OrganizationId.ORG_A, [start, start + timedelta(hours=1)]))
    with pytest.raises(ShareStoreError, match="timestamps do not match"):
        store.submit(
            time_series_submission(OrganizationId.ORG_B, [start, start + timedelta(hours=2)])
        )
    aggregate = store.aggregate("TASK-SERIES")
    assert aggregate.status == ComputeTaskStatus.FAILED
    assert aggregate.payload is None
