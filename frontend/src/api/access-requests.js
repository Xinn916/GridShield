import { request } from "./client.js";

export function createAccessRequest(payload) {
  return request("/api/v1/access-requests", { method: "POST", body: payload, timeout: 10000 });
}

export function listMyAccessRequests() {
  return request("/api/v1/access-requests/mine", { timeout: 10000 });
}

export function getAccessRequest(requestId) {
  return request(`/api/v1/access-requests/${encodeURIComponent(requestId)}`, { timeout: 10000 });
}

export function updateAccessRequest(requestId, payload) {
  return request(`/api/v1/access-requests/${encodeURIComponent(requestId)}`, {
    method: "PATCH",
    body: payload,
    timeout: 10000,
  });
}

export function submitAccessRequest(requestId) {
  return request(`/api/v1/access-requests/${encodeURIComponent(requestId)}/submit`, {
    method: "POST",
    timeout: 10000,
  });
}

export function withdrawAccessRequest(requestId) {
  return request(`/api/v1/access-requests/${encodeURIComponent(requestId)}/withdraw`, {
    method: "POST",
    timeout: 10000,
  });
}
