import test from "node:test";
import assert from "node:assert/strict";

import { normalizeApprovalRequest } from "../src/access/approval-adapter.js";

test("approval request adapter maps the real snake_case schema", () => {
  const normalized = normalizeApprovalRequest({
    request_id: "REQUEST-000001",
    requester_user_id: "analyst_demo",
    purpose: "跨园区趋势分析",
    requested_parties: ["ORG_A", "ORG_B"],
    requested_query_types: ["SUM", "TIME_SERIES"],
    requested_start_time: "2012-11-11T00:00:00",
    requested_end_time: "2012-11-13T00:00:00",
    requested_group_by: ["30m", "1h"],
    requested_max_epsilon_per_query: 2,
    requested_total_epsilon: 4,
    requested_expires_at: "2099-01-01T00:00:00",
    status: "PENDING",
  });

  assert.deepEqual(normalized, {
    requestId: "REQUEST-000001",
    requesterUserId: "analyst_demo",
    purpose: "跨园区趋势分析",
    requestedParties: "ORG_A / ORG_B",
    requestedQueryTypes: "SUM / TIME_SERIES",
    requestedStartTime: "2012-11-11T00:00:00",
    requestedEndTime: "2012-11-13T00:00:00",
    requestedGroupBy: "30m / 1h",
    maxEpsilonPerQuery: "2",
    totalEpsilon: "4",
    requestedExpiresAt: "2099-01-01T00:00:00",
    status: "PENDING",
  });
});

test("approval request adapter renders empty and object fields safely", () => {
  const normalized = normalizeApprovalRequest({ requested_group_by: [], purpose: null });
  assert.equal(normalized.requestedGroupBy, "—");
  assert.equal(normalized.purpose, "—");
  assert.equal(normalized.requestId, "—");
  assert.ok(!JSON.stringify(normalized).includes("undefined"));
  assert.ok(!JSON.stringify(normalized).includes("[object Object]"));
});
