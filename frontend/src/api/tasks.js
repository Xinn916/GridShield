import { request } from "./client.js";

// POST /api/v1/tasks —— 创建联合隐私统计任务
export function createTask(payload) {
  return request("/api/v1/tasks", { method: "POST", body: payload, timeout: 20000 });
}

// GET /api/v1/tasks/{task_id} —— 查询任务状态
export function getTask(taskId, { signal } = {}) {
  return request(`/api/v1/tasks/${encodeURIComponent(taskId)}`, { timeout: 10000, signal });
}

// GET /api/v1/tasks/{task_id}/result —— 查询任务结果
export function getTaskResult(taskId, { signal } = {}) {
  return request(`/api/v1/tasks/${encodeURIComponent(taskId)}/result`, { timeout: 10000, signal });
}

// GET /api/v1/tasks/{task_id}/monitor —— 任务监控（仅阶段与计数，无份额/明文）
export function getTaskMonitor(taskId) {
  return request(`/api/v1/tasks/${encodeURIComponent(taskId)}/monitor`, { timeout: 10000 });
}

// GET /api/v1/tasks?limit=... —— 最近任务列表
export function listTasks(limit = 10) {
  return request(`/api/v1/tasks?limit=${Number(limit) || 10}`, { timeout: 10000 });
}
