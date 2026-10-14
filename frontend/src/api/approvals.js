import { request } from "./client.js";

export function listPendingApprovals() {
  return request("/api/v1/approvals/pending", { timeout: 10000 });
}

export function listApprovalHistory() {
  return request("/api/v1/approvals/history", { timeout: 10000 });
}

export function getApproval(approvalId) {
  return request(`/api/v1/approvals/${encodeURIComponent(approvalId)}`, { timeout: 10000 });
}

export function decideApproval(approvalId, payload) {
  return request(`/api/v1/approvals/${encodeURIComponent(approvalId)}/decision`, {
    method: "POST",
    body: payload,
    timeout: 10000,
  });
}
