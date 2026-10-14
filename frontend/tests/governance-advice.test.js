import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { governanceAdvice } from "../src/api/agent.js";

const mainSource = fs.readFileSync(path.resolve("src/main.js"), "utf8");
const mockSource = fs.readFileSync(path.resolve("src/mock.js"), "utf8");

test("query results no longer render or trigger the governance advice panel", () => {
  assert.doesNotMatch(mainSource, /data-tab=\"governance\"/);
  assert.doesNotMatch(mainSource, /id=\"q-governance\"/);
  assert.doesNotMatch(mainSource, /refresh-governance/);
  assert.doesNotMatch(mainSource, /runGovernanceAdvice/);
  assert.doesNotMatch(mockSource, /budgetAdvice/);
});

test("governance API sends only a task identifier", async () => {
  const originalFetch = globalThis.fetch;
  let captured;
  globalThis.fetch = async (_url, options) => {
    captured = JSON.parse(options.body);
    return new Response(JSON.stringify({
      task_id: "TASK-000001",
      risk_level: "LOW",
      summary: "预算状态稳定。",
      suggestions: ["按现有授权范围控制重复查询。"],
    }), { status: 200, headers: { "content-type": "application/json" } });
  };
  try {
    const result = await governanceAdvice("TASK-000001");
    assert.deepEqual(captured, { task_id: "TASK-000001" });
    assert.equal(result.risk_level, "LOW");
    assert.equal(result.suggestions.length, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
