from datetime import datetime, timedelta

from common.enums import GroupBy


BUCKET_STEPS = {
    GroupBy.HALF_HOUR: timedelta(minutes=30),
    GroupBy.HOUR: timedelta(hours=1),
    GroupBy.DAY: timedelta(days=1),
}


def generate_time_buckets(
    start_time: datetime, end_time: datetime, group_by: GroupBy
) -> list[datetime]:
    if start_time >= end_time:
        raise ValueError("start_time must be earlier than end_time")
    if group_by == GroupBy.DAY:
        current = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
    elif group_by == GroupBy.HOUR:
        current = start_time.replace(minute=0, second=0, microsecond=0)
    else:
        current = start_time.replace(
            minute=30 if start_time.minute >= 30 else 0, second=0, microsecond=0
        )
    buckets = []
    while current < end_time:
        buckets.append(current)
        current += BUCKET_STEPS[group_by]
    return buckets
