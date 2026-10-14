from collections import defaultdict
from typing import Any

from common.enums import QueryType
from common.schemas import StatisticsResponse


def aggregate_results(query_type: QueryType, responses: list[StatisticsResponse]) -> dict[str, Any]:
    total_sum = sum(item.sum for item in responses)
    total_count = sum(item.count for item in responses)
    result: dict[str, Any] = {"sum": total_sum, "count": total_count}
    if query_type == QueryType.SUM:
        result["value"] = total_sum
    elif query_type == QueryType.COUNT:
        result["value"] = total_count
    elif query_type == QueryType.AVERAGE:
        result["value"] = total_sum / total_count if total_count else None
    else:
        buckets: dict[str, dict[str, float | int]] = defaultdict(lambda: {"sum": 0.0, "count": 0})
        for response in responses:
            for point in response.series or []:
                buckets[point["timestamp"]]["sum"] += point["sum"]
                buckets[point["timestamp"]]["count"] += point["count"]
        result["series"] = [
            {"timestamp": key, "sum": values["sum"], "count": values["count"]}
            for key, values in sorted(buckets.items())
        ]
    result["parties"] = [item.organization_id.value for item in responses]
    return result
