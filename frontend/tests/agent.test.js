import { test } from "node:test";
import assert from "node:assert/strict";

const { applyDraft, draftSummary } = await import("../src/agent/agent-controller.js");

const baseForm = {
  query_type: "SUM",
  parties: ["ORG_A", "ORG_B", "ORG_C"],
  start_time: "2012-11-11T00:00",
  end_time: "2012-11-12T00:00",
  epsilon: 1.0,
  group_by: "1h",
};

test("applyDraft clears group_by for SUM draft", () => {
  const draft = {
    query_type: "SUM",
    parties: ["ORG_A", "ORG_B"],
    start_time: "2012-11-11T00:00:00",
    end_time: "2012-11-12T00:00:00",
    epsilon: 0.5,
    group_by: null,
  };
  const { form, changed } = applyDraft(baseForm, draft);
  assert.equal(form.query_type, "SUM");
  assert.equal(form.group_by, null);
  assert.ok(changed.includes("group_by"));
});

test("applyDraft keeps group_by=1h for TIME_SERIES draft", () => {
  const draft = {
    query_type: "TIME_SERIES",
    parties: ["ORG_A", "ORG_B", "ORG_C"],
    start_time: "2012-11-11T00:00:00",
    end_time: "2012-11-12T00:00:00",
    epsilon: 1.0,
    group_by: "1h",
  };
  const { form, changed } = applyDraft({ ...baseForm, group_by: "" }, draft);
  assert.equal(form.query_type, "TIME_SERIES");
  assert.equal(form.group_by, "1h");
  assert.ok(changed.includes("group_by"));
});

test("applyDraft does not overwrite missing fields", () => {
  const draft = {
    query_type: "TIME_SERIES",
    parties: ["ORG_A", "ORG_B", "ORG_C"],
    start_time: null,
    end_time: null,
    epsilon: null,
    group_by: null,
  };
  const { form, changed } = applyDraft(baseForm, draft);
  assert.equal(form.start_time, "2012-11-11T00:00", "missing start_time must keep current form value");
  assert.equal(form.end_time, "2012-11-12T00:00");
  assert.equal(form.epsilon, 1.0);
  assert.ok(!changed.includes("start_time"));
  assert.ok(!changed.includes("end_time"));
});

test("applyDraft reports changed fields and updates parties", () => {
  const draft = {
    query_type: "COUNT",
    parties: ["ORG_B", "ORG_C"],
    start_time: "2012-11-11T00:00:00",
    end_time: "2012-11-12T00:00:00",
    epsilon: 0.5,
    group_by: null,
  };
  const { form, changed } = applyDraft(baseForm, draft);
  assert.deepEqual(form.parties, ["ORG_B", "ORG_C"]);
  assert.ok(changed.includes("parties"));
  assert.ok(changed.includes("query_type"));
  assert.ok(changed.includes("epsilon"));
});

test("draftSummary lists recognized rows, missing fields and warnings", () => {
  const draft = {
    query_type: "TIME_SERIES",
    parties: ["ORG_A"],
    start_time: "2012-11-11T00:00:00",
    end_time: "2012-11-12T00:00:00",
    epsilon: 1.0,
    group_by: "1h",
  };
  const summary = draftSummary(draft, {
    missing_fields: ["start_time", "end_time"],
    warnings: ["epsilon 未明确，未自动填写。"],
  });
  assert.ok(summary.rows.some((r) => r.includes("TIME_SERIES")));
  assert.ok(summary.rows.some((r) => r.includes("1h")));
  assert.equal(summary.missing.length, 2);
  assert.equal(summary.warnings.length, 1);
});
