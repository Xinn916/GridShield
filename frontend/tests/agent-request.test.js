import test from "node:test";
import assert from "node:assert/strict";
import {
  normalizeAgentCurrentForm,
  parseNaturalLanguageQuery,
} from "../src/api/agent.js";

test("agent current form converts empty optional values to null", () => {
  assert.deepEqual(normalizeAgentCurrentForm({
    grant_id: "GRANT-000004",
    query_type: "SUM",
    parties: ["ORG_B", "", "ORG_C"],
    start_time: "",
    end_time: "   ",
    epsilon: "",
    group_by: "",
  }), {
    query_type: "SUM",
    parties: ["ORG_B", "ORG_C"],
    start_time: null,
    end_time: null,
    epsilon: null,
    group_by: null,
  });
});

test("agent parse request never sends empty datetime strings", async () => {
  const originalFetch = globalThis.fetch;
  let captured;
  globalThis.fetch = async (_url, options) => {
    captured = JSON.parse(options.body);
    return new Response(JSON.stringify({ intent: "CHAT", assistant_message: "你好" }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };

  try {
    await parseNaturalLanguageQuery("你能做什么", {
      query_type: "SUM",
      parties: [],
      start_time: "",
      end_time: "",
      epsilon: null,
      group_by: "",
    });
    assert.equal(captured.current_form.start_time, null);
    assert.equal(captured.current_form.end_time, null);
    assert.equal(captured.current_form.group_by, null);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
