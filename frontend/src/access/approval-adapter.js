const EMPTY = "—";

function firstDefined(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "");
}

export function approvalDisplayValue(value, fallback = EMPTY) {
  if (value === undefined || value === null || value === "") return fallback;
  if (Array.isArray(value)) {
    const values = value.map((item) => approvalDisplayValue(item, "")).filter(Boolean);
    return values.length ? values.join(" / ") : fallback;
  }
  if (typeof value === "object") return fallback;
  return String(value);
}

// Primary names follow AccessRequestResponse from the control-plane API.
export function normalizeApprovalRequest(request = {}) {
  return {
    requestId: approvalDisplayValue(firstDefined(request.request_id, request.requestId)),
    requesterUserId: approvalDisplayValue(firstDefined(request.requester_user_id, request.requesterUserId)),
    purpose: approvalDisplayValue(request.purpose),
    requestedParties: approvalDisplayValue(firstDefined(request.requested_parties, request.requestedParties)),
    requestedQueryTypes: approvalDisplayValue(firstDefined(request.requested_query_types, request.requestedQueryTypes)),
    requestedStartTime: approvalDisplayValue(firstDefined(request.requested_start_time, request.requestedStartTime)),
    requestedEndTime: approvalDisplayValue(firstDefined(request.requested_end_time, request.requestedEndTime)),
    requestedGroupBy: approvalDisplayValue(firstDefined(request.requested_group_by, request.requestedGroupBy)),
    maxEpsilonPerQuery: approvalDisplayValue(firstDefined(request.requested_max_epsilon_per_query, request.requestedMaxEpsilonPerQuery)),
    totalEpsilon: approvalDisplayValue(firstDefined(request.requested_total_epsilon, request.requestedTotalEpsilon)),
    requestedExpiresAt: approvalDisplayValue(firstDefined(request.requested_expires_at, request.requestedExpiresAt)),
    status: approvalDisplayValue(request.status),
  };
}
