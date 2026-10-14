from common.enums import QueryType
from common.schemas import ShareBucket, SharePayload, ShareSubmission
from common.secret_sharing import PRIME


def aggregate_submissions(
    query_type: QueryType, submissions: list[ShareSubmission]
) -> SharePayload:
    if query_type in (QueryType.SUM, QueryType.COUNT):
        return SharePayload(value=sum(item.payload.value for item in submissions) % PRIME)
    if query_type == QueryType.AVERAGE:
        return SharePayload(
            sum=sum(item.payload.sum for item in submissions) % PRIME,
            count=sum(item.payload.count for item in submissions) % PRIME,
        )

    expected_timestamps = None
    buckets: dict = {}
    for submission in submissions:
        submitted = submission.payload.buckets or []
        timestamps = [item.timestamp for item in submitted]
        if expected_timestamps is None:
            expected_timestamps = timestamps
        elif timestamps != expected_timestamps:
            raise ValueError("time-series bucket timestamps do not match")
        for item in submitted:
            buckets[item.timestamp] = (buckets.get(item.timestamp, 0) + item.value) % PRIME
    return SharePayload(
        buckets=[ShareBucket(timestamp=timestamp, value=value) for timestamp, value in sorted(buckets.items())]
    )
