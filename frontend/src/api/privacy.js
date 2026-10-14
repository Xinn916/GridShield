import { request } from "./client.js";

// GET /api/v1/privacy/budgets —— 隐私预算
export function getBudget(subjectId = "demo-analyst", dataScope = "GLOBAL", { signal } = {}) {
  const query = new URLSearchParams({
    subject_id: subjectId,
    data_scope: dataScope,
  });
  return request(`/api/v1/privacy/budgets?${query.toString()}`, { timeout: 10000, signal });
}
