import { mock, test } from "node:test";
import assert from "node:assert/strict";

const { QueryController } = await import("../src/query/query-controller.js");

async function flush() {
  await new Promise((resolve) => setImmediate(resolve));
}

const validForm = {
  query_type: "SUM",
  parties: ["ORG_A", "ORG_B", "ORG_C"],
  start_time: "2012-11-11T00:00",
  end_time: "2012-11-12T00:00",
  epsilon: 1.0,
  group_by: null,
};

function makeHarness(overrides = {}) {
  const calls = { created: 0, fetched: 0, results: 0, budgets: 0, createPayloads: [] };
  const controller = new QueryController({
    onCreateTask: async (payload) => {
      calls.created += 1;
      calls.createPayloads.push(payload);
      return { task_id: "TASK-000001", status: "CREATED", ...payload };
    },
    onGetTask: async (taskId, { signal } = {}) => {
      calls.fetched += 1;
      if (signal && signal.aborted) throw new Error("aborted");
      if (overrides.getTask) return overrides.getTask(taskId, calls.fetched);
      return { task_id: taskId, status: "COMPLETED" };
    },
    onGetResult: async (taskId) => {
      calls.results += 1;
      return {
        task_id: taskId,
        status: "COMPLETED",
        query_type: "SUM",
        calculation_mode: "DISTRIBUTED_DP",
        privacy: { post_processing: [] },
        result: { value: 123.45 },
      };
    },
    onGetBudget: async () => {
      calls.budgets += 1;
      return { subject_id: "demo-analyst", data_scope: "GLOBAL", total_epsilon: 20, used_epsilon: 1, reserved_epsilon: 0, remaining_epsilon: 19 };
    },
    ...overrides,
  });
  return { controller, calls };
}

test("SUM task flow creates, completes and fetches result", async () => {
  const { controller, calls } = makeHarness();
  let finalState = null;
  const outcome = await controller.submit(validForm, {
    onState: (s) => { if (s.phase === "completed") finalState = s; },
  });
  await flush();
  assert.equal(outcome.ok, true);
  assert.equal(outcome.taskId, "TASK-000001");
  assert.equal(calls.created, 1);
  assert.equal(calls.results, 1);
  assert.equal(calls.budgets, 1, "budget must be refreshed after completion");
  assert.equal(controller.phase, "completed");
  assert.equal(controller.result.result.value, 123.45);
  assert.equal(controller.lastPayload.query_type, "SUM");
  assert.ok(!("group_by" in controller.lastPayload), "SUM lastPayload must not contain group_by");
  assert.ok(finalState);
});

test("TIME_SERIES task passes group_by through", async () => {
  const { controller, calls } = makeHarness({
    onGetResult: async (taskId) => ({
      task_id: taskId,
      status: "COMPLETED",
      query_type: "TIME_SERIES",
      calculation_mode: "DISTRIBUTED_DP",
      result: { bucket_count: 24, buckets: [], metrics: {} },
    }),
  });
  await controller.submit(
    { ...validForm, query_type: "TIME_SERIES", group_by: "1h" },
    { onState: () => {} }
  );
  await flush();
  assert.equal(calls.createPayloads[0].group_by, "1h");
  assert.equal(controller.phase, "completed");
});

test("polling stops on COMPLETED and does not fetch more", async () => {
  let fetches = 0;
  const { controller, calls } = makeHarness({
    onGetTask: async (taskId) => {
      fetches += 1;
      return { task_id: taskId, status: "COMPLETED" };
    },
  });
  await controller.submit(validForm, { onState: () => {} });
  await flush();
  assert.equal(fetches, 1);
  assert.equal(controller.phase, "completed");
});

test("polling stops on FAILED and refreshes budget", async () => {
  const { controller, calls } = makeHarness({
    onGetTask: async (taskId) => ({ task_id: taskId, status: "FAILED", error: "injected failure" }),
  });
  await controller.submit(validForm, { onState: () => {} });
  await flush();
  assert.equal(controller.phase, "failed");
  assert.equal(calls.results, 0, "result must not be fetched for failed tasks");
  assert.equal(calls.budgets, 1, "budget must be refreshed after failure");
  assert.equal(controller.error.type, "TASK_FAILED");
});

test("timeout stops polling and never creates a duplicate task", async (t) => {
  mock.timers.enable({ apis: ["setTimeout", "Date"] });
  t.after(() => mock.timers.reset());
  const { controller, calls } = makeHarness({
    onGetTask: async (taskId) => ({ task_id: taskId, status: "RUNNING" }),
    pollIntervalMs: 1000,
    maxWaitMs: 3000,
  });
  await controller.submit(validForm, { onState: () => {} });
  await flush();
  await mock.timers.tick(1000);
  await flush();
  await mock.timers.tick(1000);
  await flush();
  await mock.timers.tick(1000);
  await flush();
  assert.equal(controller.phase, "timeout");
  assert.equal(controller.error.type, "TIMEOUT");
  assert.equal(calls.created, 1, "timeout must not create another task");
  await mock.timers.tick(10000);
  assert.equal(calls.created, 1);
});

test("dispose() aborts in-flight requests and stops polling", async (t) => {
  mock.timers.enable({ apis: ["setTimeout", "Date"] });
  t.after(() => mock.timers.reset());
  let fetches = 0;
  let seenSignal = null;
  const { controller } = makeHarness({
    onGetTask: async (taskId, { signal } = {}) => {
      fetches += 1;
      seenSignal = signal;
      return { task_id: taskId, status: "RUNNING" };
    },
    pollIntervalMs: 1000,
    maxWaitMs: 60000,
  });
  await controller.submit(validForm, { onState: () => {} });
  await flush();
  controller.dispose();
  assert.equal(seenSignal.aborted, true);
  await mock.timers.tick(5000);
  assert.equal(fetches, 1);
});

test("double submit is blocked while busy", async () => {
  let resolveCreate;
  const controller = new QueryController({
    onCreateTask: () => new Promise((resolve) => { resolveCreate = resolve; }),
    onGetTask: async (taskId) => ({ task_id: taskId, status: "RUNNING" }),
    onGetResult: async () => ({}),
    onGetBudget: async () => ({}),
    pollIntervalMs: 60000,
    maxWaitMs: 60000,
  });
  const first = controller.submit(validForm, { onState: () => {} });
  const second = await controller.submit(validForm, { onState: () => {} });
  assert.equal(second.ok, false);
  assert.equal(second.reason, "BUSY");
  resolveCreate({ task_id: "TASK-1", status: "CREATED" });
  await first;
});

test("validation errors are returned without creating a task", async () => {
  const { controller, calls } = makeHarness();
  const outcome = await controller.submit({ ...validForm, epsilon: 99 }, { onState: () => {} });
  assert.equal(outcome.ok, false);
  assert.equal(outcome.reason, "VALIDATION");
  assert.equal(calls.created, 0);
  assert.equal(controller.phase, "validation_error");
});

test("budget insufficient (409) is surfaced and budget is refreshed", async () => {
  const { controller, calls } = makeHarness({
    onCreateTask: async () => {
      const error = new Error("insufficient privacy budget");
      error.status = 409;
      throw error;
    },
  });
  const outcome = await controller.submit(validForm, { onState: () => {} });
  assert.equal(outcome.ok, false);
  assert.equal(outcome.reason, "budget_insufficient");
  assert.equal(controller.error.type, "BUDGET_INSUFFICIENT");
  assert.equal(calls.budgets, 1);
});

test("POST failure does not start polling and does not fetch result", async () => {
  const { controller, calls } = makeHarness({
    onCreateTask: async () => {
      calls.created += 1;
      const error = new Error("创建任务失败");
      error.status = 500;
      throw error;
    },
  });
  await controller.submit(validForm, { onState: () => {} });
  assert.equal(controller.phase, "error");
  assert.equal(calls.fetched, 0, "polling must not start when POST /tasks fails");
  assert.equal(calls.results, 0, "result must not be fetched when POST /tasks fails");
  assert.equal(calls.created, 1);
  assert.equal(controller.task, null);
});

test("polling starts only after POST /tasks returns task_id", async () => {
  let resolveCreate;
  let fetched = 0;
  const controller = new QueryController({
    onCreateTask: () => new Promise((resolve) => { resolveCreate = resolve; }),
    onGetTask: async (taskId) => {
      fetched += 1;
      return { task_id: taskId, status: "COMPLETED" };
    },
    onGetResult: async () => ({ task_id: "TASK-X", status: "COMPLETED", query_type: "SUM", result: { value: 1 } }),
    onGetBudget: async () => ({ remaining_epsilon: 19 }),
    pollIntervalMs: 1000,
    maxWaitMs: 60000,
  });
  const pending = controller.submit(validForm, { onState: () => {} });
  await flush();
  assert.equal(fetched, 0, "no polling before task_id is returned");
  resolveCreate({ task_id: "TASK-X", status: "CREATED" });
  await pending;
  await flush();
  assert.equal(fetched, 1, "polling starts only after task_id is available");
  assert.equal(controller.phase, "completed");
});
