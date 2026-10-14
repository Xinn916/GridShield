import { test } from "node:test";
import assert from "node:assert/strict";

process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://backend.test:8000";

const { createTask, getTaskResult, listTasks } = await import("../src/api/tasks.js");
const { validateQueryForm, toTaskPayload, resolveGroupBy } = await import("../src/query/query-controller.js");

function installFetch(capture) {
  globalThis.fetch = async (url, options) => {
    capture({ url: String(url), options });
    return new Response(JSON.stringify({ task_id: "TASK-000001", status: "CREATED" }), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });
  };
}

const validForm = {
  query_type: "SUM",
  parties: ["ORG_A", "ORG_B", "ORG_C"],
  start_time: "2012-11-11T00:00",
  end_time: "2012-11-12T00:00",
  epsilon: 1.0,
  group_by: null,
};

test("SUM task payload is created correctly", async () => {
  let captured = null;
  installFetch((c) => { captured = c; });
  const payload = toTaskPayload({ ...validForm, query_type: "SUM", group_by: "1h" });
  assert.equal(payload.query_type, "SUM");
  assert.ok(!("group_by" in payload), "SUM payload must not contain group_by");
  assert.deepEqual(payload.parties, ["ORG_A", "ORG_B", "ORG_C"]);
  assert.equal(payload.start_time, "2012-11-11T00:00:00");
  await createTask(payload);
  const body = JSON.parse(captured.options.body);
  assert.equal(body.query_type, "SUM");
  assert.ok(!("group_by" in body), "SUM request JSON must not contain group_by");
});

test("COUNT and AVERAGE payloads do not contain group_by", async () => {
  for (const queryType of ["COUNT", "AVERAGE"]) {
    let captured = null;
    installFetch((c) => { captured = c; });
    const payload = toTaskPayload({ ...validForm, query_type: queryType, group_by: "1h" });
    assert.ok(!("group_by" in payload), `${queryType} payload must not contain group_by`);
    await createTask(payload);
    const body = JSON.parse(captured.options.body);
    assert.ok(!("group_by" in body), `${queryType} request JSON must not contain group_by`);
  }
});

test("TIME_SERIES task payload passes group_by", async () => {
  let captured = null;
  installFetch((c) => { captured = c; });
  const payload = toTaskPayload({ ...validForm, query_type: "TIME_SERIES", group_by: "1h" });
  assert.equal(payload.group_by, "1h");
  await createTask(payload);
  const body = JSON.parse(captured.options.body);
  assert.equal(body.query_type, "TIME_SERIES");
  assert.equal(body.group_by, "1h");
});

test("resolveGroupBy clears group_by when switching from TIME_SERIES to SUM", () => {
  assert.equal(resolveGroupBy("TIME_SERIES", "1h"), "1h");
  assert.equal(resolveGroupBy("SUM", "1h"), null);
  assert.equal(resolveGroupBy("COUNT", "30m"), null);
  assert.equal(resolveGroupBy("AVERAGE", "1d"), null);
});

test("validation rejects TIME_SERIES without group_by", () => {
  const result = validateQueryForm({ ...validForm, query_type: "TIME_SERIES", group_by: null });
  assert.equal(result.ok, false);
  assert.ok(result.errors.some((e) => e.includes("group_by")));
});

test("validation rejects group_by on non-TIME_SERIES", () => {
  const result = validateQueryForm({ ...validForm, query_type: "SUM", group_by: "1h" });
  assert.equal(result.ok, false);
  assert.ok(result.errors.some((e) => e.includes("group_by")));
});

test("validation rejects epsilon outside (0, 5]", () => {
  for (const epsilon of [0, -1, 6]) {
    const result = validateQueryForm({ ...validForm, epsilon });
    assert.equal(result.ok, false, `epsilon=${epsilon} should fail`);
  }
  assert.equal(validateQueryForm({ ...validForm, epsilon: 5 }).ok, true);
});

test("validation rejects empty parties and reversed time range", () => {
  const emptyParties = validateQueryForm({ ...validForm, parties: [] });
  assert.equal(emptyParties.ok, false);
  const reversed = validateQueryForm({
    ...validForm,
    start_time: "2012-11-12T00:00",
    end_time: "2012-11-11T00:00",
  });
  assert.equal(reversed.ok, false);
});

test("getTaskResult hits the result endpoint", async () => {
  let captured = null;
  installFetch((c) => { captured = c; });
  await getTaskResult("TASK-000001");
  assert.equal(captured.url, "http://backend.test:8000/api/v1/tasks/TASK-000001/result");
});

test("listTasks sends limit query", async () => {
  let captured = null;
  installFetch((c) => { captured = c; });
  await listTasks(50);
  assert.equal(captured.url, "http://backend.test:8000/api/v1/tasks?limit=50");
});
