import { test } from "node:test";
import assert from "node:assert/strict";

process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://api.example";

test("performance API uses the authenticated backend routes", async () => {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url: String(url), options });
    return new Response(JSON.stringify({ id: "PERF-1", status: "COMPLETED", items: [] }), {
      status: 200, headers: { "Content-Type": "application/json" },
    });
  };
  const { PERFORMANCE_API_STATUS, performanceApi } = await import(`../src/api/performance.js?${Date.now()}`);
  assert.equal(PERFORMANCE_API_STATUS, "AVAILABLE");
  await performanceApi.startTest({ benchmark_id: "ENERGY_BENCHMARK_V1" });
  await performanceApi.getTest("PERF-1");
  await performanceApi.listTests({ limit: 5, offset: 10 });
  assert.deepEqual(calls.map((item) => item.url), [
    "http://api.example/api/v1/performance-tests",
    "http://api.example/api/v1/performance-tests/PERF-1",
    "http://api.example/api/v1/performance-tests?limit=5&offset=10",
  ]);
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls.every((item) => item.options.credentials === "include"), true);
});
