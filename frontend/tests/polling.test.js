import { mock, test } from "node:test";
import assert from "node:assert/strict";

const { createTaskPoller } = await import("../src/utils/polling.js");

async function flush() {
  await new Promise((resolve) => setImmediate(resolve));
}

test("polling stops when task reaches COMPLETED", async (t) => {
  mock.timers.enable({ apis: ["setTimeout", "Date"] });
  t.after(() => mock.timers.reset());
  let calls = 0;
  const events = [];
  const poller = createTaskPoller({
    taskId: "TASK-1",
    fetchTask: async () => {
      calls += 1;
      return calls === 1 ? { task_id: "TASK-1", status: "LOCAL_COMPUTING" } : { task_id: "TASK-1", status: "COMPLETED" };
    },
    intervalMs: 1000,
    maxWaitMs: 60000,
    onUpdate: (task) => events.push(["update", task.status]),
    onComplete: (task) => events.push(["complete", task.status]),
  });
  poller.start();
  await flush();
  await mock.timers.tick(1000);
  await flush();
  assert.deepEqual(events, [
    ["update", "LOCAL_COMPUTING"],
    ["update", "COMPLETED"],
    ["complete", "COMPLETED"],
  ]);
  await mock.timers.tick(5000);
  await flush();
  assert.equal(calls, 2);
  assert.equal(poller.isFinished(), true);
});

test("polling stops when task reaches FAILED", async (t) => {
  mock.timers.enable({ apis: ["setTimeout", "Date"] });
  t.after(() => mock.timers.reset());
  let calls = 0;
  const events = [];
  const poller = createTaskPoller({
    taskId: "TASK-2",
    fetchTask: async () => {
      calls += 1;
      return { task_id: "TASK-2", status: "FAILED", error: "boom" };
    },
    intervalMs: 1000,
    maxWaitMs: 60000,
    onFailed: (task) => events.push(["failed", task.status]),
  });
  poller.start();
  await flush();
  assert.deepEqual(events, [["failed", "FAILED"]]);
  await mock.timers.tick(5000);
  assert.equal(calls, 1);
});

test("polling times out without retrying and without creating tasks", async (t) => {
  mock.timers.enable({ apis: ["setTimeout", "Date"] });
  t.after(() => mock.timers.reset());
  let calls = 0;
  let timedOut = null;
  const poller = createTaskPoller({
    taskId: "TASK-3",
    fetchTask: async () => {
      calls += 1;
      return { task_id: "TASK-3", status: "RUNNING" };
    },
    intervalMs: 1000,
    maxWaitMs: 3000,
    onTimeout: (task) => { timedOut = task; },
  });
  poller.start();
  await flush();
  await mock.timers.tick(1000);
  await flush();
  await mock.timers.tick(1000);
  await flush();
  await mock.timers.tick(1000);
  await flush();
  assert.ok(timedOut);
  const callsAtTimeout = calls;
  await mock.timers.tick(10000);
  assert.equal(calls, callsAtTimeout, "polling must stop after timeout");
});

test("stop() cancels polling (page unload)", async (t) => {
  mock.timers.enable({ apis: ["setTimeout", "Date"] });
  t.after(() => mock.timers.reset());
  let calls = 0;
  const poller = createTaskPoller({
    taskId: "TASK-4",
    fetchTask: async () => {
      calls += 1;
      return { task_id: "TASK-4", status: "RUNNING" };
    },
    intervalMs: 1000,
    maxWaitMs: 60000,
  });
  poller.start();
  await flush();
  poller.stop();
  await mock.timers.tick(5000);
  assert.equal(calls, 1);
  assert.equal(poller.isStopped(), true);
});
