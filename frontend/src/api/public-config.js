import { request } from "./client.js";

export function getPublicRuntimeConfig() {
  return request("/api/v1/public/config", { timeout: 5000 });
}
