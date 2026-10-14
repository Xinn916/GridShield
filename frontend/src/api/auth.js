import { request } from "./client.js";

export function login(username, password) {
  return request("/api/v1/auth/login", {
    method: "POST",
    body: { username, password },
    timeout: 10000,
  });
}

export function logout() {
  return request("/api/v1/auth/logout", { method: "POST", timeout: 10000 });
}

export function getCurrentUser() {
  return request("/api/v1/auth/me", { timeout: 10000 });
}
