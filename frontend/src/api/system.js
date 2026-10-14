import { request } from "./client.js";

// GET /api/v1/system/health —— 六个服务健康检查
export function getSystemHealth() {
  return request("/api/v1/system/health", { timeout: 15000 });
}

export function getSystemPolicySummary() {
  return request("/api/v1/system/policy-summary", { timeout: 15000 });
}
