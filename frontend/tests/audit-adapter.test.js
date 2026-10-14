import test from "node:test";
import assert from "node:assert/strict";

import {
  auditRecordSearchText,
  normalizeAuditRecord,
  normalizeTaskAudit,
  safeAuditValue,
} from "../src/audit/audit-adapter.js";

test("normalizes the real snake_case security audit response", () => {
  const record = normalizeAuditRecord({
    audit_id: 9,
    event_type: "TASK_CREATED_WITH_GRANT",
    actor_user_id: "analyst_demo",
    actor_role: "ANALYST",
    party_id: null,
    request_id: "REQ-9",
    grant_id: "GRANT-9",
    task_id: "TASK-9",
    decision: "CREATED",
    reason: null,
    timestamp: "2026-08-02T10:00:00Z",
  });

  assert.equal(record.auditId, "9");
  assert.equal(record.eventType, "TASK_CREATED_WITH_GRANT");
  assert.equal(record.actor, "analyst_demo");
  assert.equal(record.taskId, "TASK-9");
  assert.equal(record.grantId, "GRANT-9");
  assert.equal(record.requestId, "REQ-9");
  assert.equal(record.result, "CREATED");
  assert.equal(record.partyId, "—");
  assert.equal(record.description, "未记录");
  assert.match(auditRecordSearchText(record), /task-9/);
});

test("supports camelCase compatibility and never leaks object coercion", () => {
  const record = normalizeAuditRecord({
    auditId: "A-1",
    eventType: "CHECK",
    actor: { id: "service-a" },
    taskId: null,
    metadata: { source: "policy" },
    createdAt: "2026-08-02T10:00:00Z",
  });

  assert.equal(record.actor, '{"id":"service-a"}');
  assert.equal(record.taskId, "—");
  assert.equal(record.description, '{"source":"policy"}');
  assert.ok(!JSON.stringify(record).includes("[object Object]"));
  assert.equal(safeAuditValue(undefined), "—");
});

test("normalizes the real task and budget audit response", () => {
  const task = normalizeTaskAudit({
    task_id: "TASK-000006",
    query_type: "SUM",
    parties: ["ORG_A"],
    budget_before: 20,
    budget_after: 19,
    status: "COMPLETED",
    created_at: "2026-08-02T10:00:00Z",
  });

  assert.equal(task.taskId, "TASK-000006");
  assert.equal(task.queryType, "SUM");
  assert.deepEqual(task.parties, ["ORG_A"]);
  assert.equal(task.budgetBefore, 20);
  assert.equal(task.budgetAfter, 19);
  assert.equal(task.status, "COMPLETED");
});
