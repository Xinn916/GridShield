import { request } from "./client.js";

export function getMyAnalystReport(limit = 20) {
  return request(`/api/v1/reports/me?limit=${Number(limit) || 20}`, { timeout: 15000 });
}
