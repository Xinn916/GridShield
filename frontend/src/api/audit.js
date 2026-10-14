import { request } from "./client.js";

// GET /api/v1/audit/events —— 审计事件列表（安全字段，不含敏感数据）
export function listAuditEvents(limit = 100) {
  return request(`/api/v1/audit/events?limit=${Number(limit) || 100}`, { timeout: 10000 });
}

// GET /api/v1/audit/events/{task_id} —— 单条审计事件
export function getAuditEvent(taskId) {
  return request(`/api/v1/audit/events/${encodeURIComponent(taskId)}`, { timeout: 10000 });
}
