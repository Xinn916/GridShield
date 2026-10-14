import { request } from "./client.js";

export function listAllAccessRequests() {
  return request("/api/v1/admin/access-requests", { timeout: 10000 });
}

export function listAllGrants() {
  return request("/api/v1/admin/grants", { timeout: 10000 });
}

export function listAdminUsers() {
  return request("/api/v1/admin/users", { timeout: 10000 });
}

export function createAdminUser(payload) {
  return request("/api/v1/admin/users", {
    method: "POST",
    body: payload,
    timeout: 10000,
  });
}

export function updateAdminUser(userId, payload) {
  return request(`/api/v1/admin/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    body: payload,
    timeout: 10000,
  });
}

export function setAdminUserStatus(userId, active) {
  return request(`/api/v1/admin/users/${encodeURIComponent(userId)}/status`, {
    method: "PATCH",
    body: { active },
    timeout: 10000,
  });
}

export function resetAdminUserPassword(userId, password) {
  return request(`/api/v1/admin/users/${encodeURIComponent(userId)}/reset-password`, {
    method: "POST",
    body: { password },
    timeout: 10000,
  });
}

export function revokeAdminUserSessions(userId) {
  return request(`/api/v1/admin/users/${encodeURIComponent(userId)}/revoke-sessions`, {
    method: "POST",
    timeout: 10000,
  });
}

export function listSecurityAudit() {
  return request("/api/v1/admin/security-audit", { timeout: 10000 });
}

export function getAdminSystemOverview() {
  return request("/api/v1/admin/system-overview", { timeout: 15000 });
}
