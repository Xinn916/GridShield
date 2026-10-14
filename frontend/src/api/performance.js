import { request } from "./client.js";

export const PERFORMANCE_API_STATUS = "AVAILABLE";

export const performanceApi = {
  startTest(payload, options = {}) {
    return request("/api/v1/performance-tests", { method: "POST", body: payload, timeout: 120000, ...options });
  },
  getTest(testId, options = {}) {
    return request(`/api/v1/performance-tests/${encodeURIComponent(testId)}`, options);
  },
  listTests({ limit = 10, offset = 0 } = {}, options = {}) {
    return request(`/api/v1/performance-tests?limit=${limit}&offset=${offset}`, options);
  },
  getNodeMetrics() {
    return Promise.resolve(null);
  },
};
