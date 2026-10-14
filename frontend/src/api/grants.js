import { request } from "./client.js";

export function listMyGrants() {
  return request("/api/v1/grants/mine", { timeout: 10000 });
}

export function listOwnerGrants() {
  return request("/api/v1/grants/owner", { timeout: 10000 });
}

export function getGrant(grantId, { signal } = {}) {
  return request(`/api/v1/grants/${encodeURIComponent(grantId)}`, { timeout: 10000, signal });
}

export function revokeGrant(grantId) {
  return request(`/api/v1/grants/${encodeURIComponent(grantId)}/revoke`, {
    method: "POST",
    timeout: 10000,
  });
}
