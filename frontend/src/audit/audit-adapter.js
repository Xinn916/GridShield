const EMPTY_VALUE = "—";

function firstDefined(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "");
}

export function safeAuditValue(value, fallback = EMPTY_VALUE) {
  if (value === undefined || value === null || value === "") return fallback;
  if (Array.isArray(value)) {
    const items = value.map((item) => safeAuditValue(item, "")).filter(Boolean);
    return items.length ? items.join("、") : fallback;
  }
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return fallback;
    }
  }
  return String(value);
}

// The primary field names follow GET /api/v1/admin/security-audit.
// camelCase fallbacks keep the view resilient without inventing missing data.
export function normalizeAuditRecord(record = {}) {
  const details = firstDefined(record.reason, record.details, record.metadata);
  return {
    auditId: safeAuditValue(firstDefined(record.audit_id, record.auditId)),
    eventType: safeAuditValue(firstDefined(record.event_type, record.eventType)),
    timestamp: safeAuditValue(firstDefined(record.timestamp, record.created_at, record.createdAt)),
    actor: safeAuditValue(firstDefined(record.actor_user_id, record.actorUserId, record.actor)),
    actorRole: safeAuditValue(firstDefined(record.actor_role, record.actorRole)),
    partyId: safeAuditValue(firstDefined(record.party_id, record.partyId)),
    taskId: safeAuditValue(firstDefined(record.task_id, record.taskId)),
    grantId: safeAuditValue(firstDefined(record.grant_id, record.grantId)),
    requestId: safeAuditValue(firstDefined(record.request_id, record.requestId)),
    result: safeAuditValue(firstDefined(record.decision, record.status, record.result)),
    description: safeAuditValue(details, "未记录"),
    raw: record,
  };
}

// The primary field names follow GET /api/v1/audit/events.
export function normalizeTaskAudit(record = {}) {
  return {
    taskId: safeAuditValue(firstDefined(record.task_id, record.taskId)),
    queryType: safeAuditValue(firstDefined(record.query_type, record.queryType)),
    groupBy: safeAuditValue(firstDefined(record.group_by, record.groupBy)),
    bucketCount: firstDefined(record.bucket_count, record.bucketCount) ?? null,
    parties: Array.isArray(record.parties) ? record.parties.map((item) => safeAuditValue(item)) : [],
    epsilon: record.epsilon ?? null,
    sensitivity: record.sensitivity ?? null,
    mechanism: safeAuditValue(record.mechanism),
    privacyUnit: safeAuditValue(firstDefined(record.privacy_unit, record.privacyUnit)),
    calculationMode: safeAuditValue(firstDefined(record.calculation_mode, record.calculationMode)),
    budgetBefore: firstDefined(record.budget_before, record.budgetBefore) ?? null,
    budgetAfter: firstDefined(record.budget_after, record.budgetAfter) ?? null,
    executionTimeMs: firstDefined(record.execution_time_ms, record.executionTimeMs) ?? null,
    status: safeAuditValue(record.status),
    createdAt: safeAuditValue(firstDefined(record.created_at, record.createdAt)),
    raw: record,
  };
}

export function auditRecordSearchText(record) {
  return [
    record.eventType,
    record.actor,
    record.taskId,
    record.grantId,
    record.requestId,
    record.result,
    record.description,
  ].join(" ").toLowerCase();
}
