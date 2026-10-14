import { test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

// 真实执行 main.js 的 DOM 冒烟测试：验证页面渲染、登录流程与导航不抛异常。
process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://127.0.0.1:8000";

const testUser = { user_id: "analyst_demo", username: "analyst_demo", role: "ANALYST", party_id: null, is_active: true };
const testGrant = {
  grant_id: "GRANT-TEST", request_id: "REQUEST-TEST", grantee_user_id: "analyst_demo",
  parties: ["ORG_A", "ORG_B", "ORG_C"], allowed_query_types: ["SUM", "COUNT", "AVERAGE", "TIME_SERIES"],
  allowed_start_time: "2012-11-11T00:00:00", allowed_end_time: "2012-11-12T00:00:00",
  allowed_group_by: ["30m", "1h", "1d"], max_epsilon_per_query: 5, total_epsilon_limit: 20,
  epsilon_consumed: 0, epsilon_reserved: 0, epsilon_remaining: 20, valid_from: "2012-01-01T00:00:00",
  expires_at: "2099-01-01T00:00:00", status: "ACTIVE", created_at: "2012-01-01T00:00:00", revoked_at: null,
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

function withAuth(handler) {
  let loggedIn = false;
  return async (url, options = {}) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    if (path === "/api/v1/auth/me") return json(loggedIn ? testUser : { detail: "请先登录" }, loggedIn ? 200 : 401);
    if (path === "/api/v1/auth/login") { loggedIn = true; return json(testUser); }
    if (path === "/api/v1/auth/logout") { loggedIn = false; return new Response(null, { status: 204 }); }
    if (path === "/api/v1/grants/mine") return json([testGrant]);
    return handler(url, options);
  };
}

function setupDom() {
  const dom = new JSDOM(
    `<!DOCTYPE html><html><head></head><body><div id="app"></div></body></html>`,
    { url: "http://localhost:5173/", pretendToBeVisual: true }
  );
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.HTMLElement = dom.window.HTMLElement;
  globalThis.Element = dom.window.Element;
  globalThis.Node = dom.window.Node;
  globalThis.MouseEvent = dom.window.MouseEvent;
  globalThis.Event = dom.window.Event;
  globalThis.fetch = withAuth(async (url) => json({ detail: `unexpected ${url}` }, 404));
  return dom;
}

function click(selector) {
  const el = document.querySelector(selector);
  assert.ok(el, `element not found: ${selector}`);
  el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
}

async function settle(ms = 120) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function loginToPlatform() {
  document.querySelector("#login-username").value = "analyst_demo";
  document.querySelector("#login-password").value = "test-password";
  document.querySelector("#login-form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await settle();
}

test("app boots to login page and login flow enters the platform", async () => {
  setupDom();
  await import(`../src/main.js?smoke=${Date.now()}`);
  assert.ok(document.querySelector("#app .login-page"), "login page should render");
  await loginToPlatform();
  assert.ok(document.querySelector(".topbar"), "topbar should render after login");
  assert.ok(document.querySelector(".sidebar"), "sidebar should render after login");
});

test("real pages render without throwing when mock is off", async (t) => {
  setupDom();
  await import(`../src/main.js?smoke2=${Date.now()}`);
  await loginToPlatform();

  click('[data-page="query"]');
  assert.ok(document.querySelector("#q-type"), "query form should render");
  assert.ok(document.querySelector("#q-submit"), "query submit button should render");
  await settle();
  assert.equal(document.querySelectorAll("#q-parties .access-option").length, 3, "query parties should use compact options");
  assert.deepEqual(Array.from(document.querySelectorAll("#q-parties .access-option > span"), (item) => item.textContent), ["ORG_A", "ORG_B", "ORG_C"]);

  click('[data-page="overview"]');
  assert.ok(document.querySelector("main.content"), "overview should render");
  await settle();

  click('[data-page="compute"]');
  assert.ok(document.querySelector("main.content h2"), "compute page should render");
  await settle();

  click('[data-page="catalog"]');
  assert.ok(document.querySelector("main.content h2"), "analyst catalog page should render");
  await settle();

  click('[data-page="query"]');
  assert.ok(document.querySelector("#q-type"), "back to query page");
});

test("query flow updates the DOM from controller state (fake backend)", async () => {
  setupDom();
  const realFetch = globalThis.fetch;
  globalThis.fetch = withAuth(async (url, options = {}) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    const json = (data, status = 200) =>
      new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
    if (path.startsWith("/api/v1/privacy/budgets")) {
      return json({ subject_id: "demo-analyst", data_scope: "GLOBAL", total_epsilon: 20, used_epsilon: 1, reserved_epsilon: 0, remaining_epsilon: 19 });
    }
    if (options.method === "POST" && path === "/api/v1/tasks") {
      return json({
        task_id: "TASK-TEST-1",
        status: "CREATED",
        query_type: "TIME_SERIES",
        parties: ["ORG_A", "ORG_B", "ORG_C"],
        calculation_mode: "DISTRIBUTED_DP",
        epsilon: 1.0,
        mechanism: "distributed_vector_laplace",
        privacy_unit: "household",
      }, 201);
    }
    if (path === "/api/v1/tasks/TASK-TEST-1") {
      return json({
        task_id: "TASK-TEST-1",
        status: "COMPLETED",
        query_type: "TIME_SERIES",
        parties: ["ORG_A", "ORG_B", "ORG_C"],
        calculation_mode: "DISTRIBUTED_DP",
        epsilon: 1.0,
        mechanism: "distributed_vector_laplace",
        privacy_unit: "household",
        duration_ms: 520,
        error: null,
      });
    }
    if (path === "/api/v1/tasks/TASK-TEST-1/result") {
      return json({
        task_id: "TASK-TEST-1",
        status: "COMPLETED",
        query_type: "TIME_SERIES",
        calculation_mode: "DISTRIBUTED_DP",
        privacy: { post_processing: ["non_negative_clamp", "load_metrics"] },
        result: {
          group_by: "1h",
          bucket_count: 2,
          buckets: [
            { timestamp: "2012-11-11T00:00:00", value: 1.5 },
            { timestamp: "2012-11-11T01:00:00", value: 2.5 },
          ],
          metrics: {
            peak_value: 2.5,
            peak_timestamp: "2012-11-11T01:00:00",
            valley_value: 1.5,
            valley_timestamp: "2012-11-11T00:00:00",
            peak_valley_difference: 1.0,
            average_load: 2.0,
            load_factor: 0.6,
          },
        },
      });
    }
    return json({ detail: `unexpected request ${path}` }, 404);
  });

  try {
    await import(`../src/main.js?smoke4=${Date.now()}`);
    await loginToPlatform();
    click('[data-page="query"]');
    await settle();
    document.querySelector("#q-type").value = "TIME_SERIES";
    document.querySelector("#q-group").value = "1h";
    click("#q-submit");

    let updated = false;
    for (let i = 0; i < 20; i++) {
      await settle(100);
      const text = document.querySelector("#q-result")?.textContent || "";
      if (text.includes("时间桶数量") && text.includes("峰值负荷")) {
        updated = true;
        break;
      }
    }
    assert.ok(updated, "result panel should show bucket metrics from controller state");
    assert.ok(
      (document.querySelector("#q-status")?.textContent || "").includes("TASK-TEST-1"),
      "status should show the created task id"
    );
    const privacy = document.querySelector("#q-privacy")?.textContent || "";
    assert.ok(privacy.includes("分布式向量拉普拉斯机制"), "privacy panel should show Chinese mechanism label");
    assert.ok(privacy.includes("非负后处理") && privacy.includes("负荷指标后处理"), "privacy panel should show post-processing labels");
  } finally {
    globalThis.fetch = realFetch;
  }
});

test("SUM flow omits group_by and hides the granularity control", async () => {
  setupDom();
  const realFetch = globalThis.fetch;
  const postBodies = [];
  let taskResult = null;
  globalThis.fetch = withAuth(async (url, options = {}) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    const json = (data, status = 200) =>
      new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
    if (path.startsWith("/api/v1/privacy/budgets")) {
      return json({ subject_id: "demo-analyst", data_scope: "GLOBAL", total_epsilon: 20, used_epsilon: 1, reserved_epsilon: 0, remaining_epsilon: 19 });
    }
    if (options.method === "POST" && path === "/api/v1/tasks") {
      const body = JSON.parse(options.body);
      postBodies.push(body);
      const taskId = body.query_type === "SUM" ? "TASK-SUM-1" : "TASK-TS-1";
      return json({
        task_id: taskId,
        status: "CREATED",
        query_type: body.query_type,
        parties: body.parties,
        epsilon: body.epsilon,
        calculation_mode: "DISTRIBUTED_DP",
        mechanism: body.query_type === "SUM" ? "distributed_laplace" : "distributed_vector_laplace",
        privacy_unit: "household",
        sensitivity: 240,
      }, 201);
    }
    const taskIdMatch = path.match(/^\/api\/v1\/tasks\/(TASK-[A-Z0-9-]+)$/);
    if (taskIdMatch) {
      return json({
        task_id: taskIdMatch[1],
        status: "COMPLETED",
        query_type: taskResult?.query_type || "SUM",
        parties: ["ORG_A", "ORG_B", "ORG_C"],
        calculation_mode: "DISTRIBUTED_DP",
        epsilon: 1.0,
        sensitivity: 240,
        privacy_unit: "household",
        mechanism: taskResult?.query_type === "TIME_SERIES" ? "distributed_vector_laplace" : "distributed_laplace",
        duration_ms: 300,
        error: null,
      });
    }
    if (path.startsWith("/api/v1/tasks/") && path.endsWith("/result")) {
      return json(taskResult);
    }
    return json({ detail: `unexpected request ${path}` }, 404);
  });

  try {
    await import(`../src/main.js?sumflow=${Date.now()}`);
    await loginToPlatform();
    click('[data-page="query"]');
    await settle();

    assert.equal(document.querySelector("#q-type").value, "SUM");
    const groupWrap = document.querySelector("#q-group-wrap");
    const groupSelect = document.querySelector("#q-group");
    assert.equal(groupWrap.style.display, "none", "granularity control should be hidden for SUM");
    assert.equal(groupSelect.disabled, true, "granularity control should be disabled for SUM");

    taskResult = {
      task_id: "TASK-SUM-1",
      status: "COMPLETED",
      query_type: "SUM",
      calculation_mode: "DISTRIBUTED_DP",
      privacy: { post_processing: ["non_negative_clamp"] },
      result: { value: 1234.5 },
    };
    click("#q-submit");
    let sumRendered = false;
    for (let i = 0; i < 20; i++) {
      await settle(100);
      if ((document.querySelector("#q-result")?.textContent || "").includes("kWh（带噪总用电量）")) {
        sumRendered = true;
        break;
      }
    }
    assert.ok(sumRendered, "SUM result should render");
    assert.equal(postBodies.length, 1);
    assert.equal(postBodies[0].query_type, "SUM");
    assert.ok(!("group_by" in postBodies[0]), "SUM request JSON must not contain group_by");
    const sumText = document.querySelector("#q-result").textContent;
    assert.match(sumText, /1,234\.5/);
    assert.ok((document.querySelector("#q-status")?.textContent || "").includes("TASK-SUM-1"));
    assert.ok((document.querySelector("#q-privacy")?.textContent || "").includes("分布式拉普拉斯机制"));

    // 切到 TIME_SERIES：恢复控件并默认 1h，请求携带 group_by。
    const typeSelect = document.querySelector("#q-type");
    typeSelect.value = "TIME_SERIES";
    typeSelect.dispatchEvent(new Event("change", { bubbles: true }));
    assert.equal(groupWrap.style.display, "", "granularity control should be visible for TIME_SERIES");
    assert.equal(groupSelect.disabled, false);
    assert.equal(groupSelect.value, "1h", "TIME_SERIES default granularity should be 1h");

    taskResult = {
      task_id: "TASK-TS-1",
      status: "COMPLETED",
      query_type: "TIME_SERIES",
      calculation_mode: "DISTRIBUTED_DP",
      privacy: { post_processing: ["non_negative_clamp", "load_metrics"] },
      result: {
        group_by: "1h",
        bucket_count: 24,
        buckets: [{ timestamp: "2012-11-11T00:00:00", value: 1 }, { timestamp: "2012-11-11T01:00:00", value: 2 }],
        metrics: { peak_value: 2, peak_timestamp: "2012-11-11T01:00:00", valley_value: 1, valley_timestamp: "2012-11-11T00:00:00", peak_valley_difference: 1, average_load: 1.5, load_factor: 0.6 },
      },
    };
    click("#q-submit");
    let tsRendered = false;
    for (let i = 0; i < 20; i++) {
      await settle(100);
      if ((document.querySelector("#q-result")?.textContent || "").includes("时间桶数量")) {
        tsRendered = true;
        break;
      }
    }
    assert.ok(tsRendered, "TIME_SERIES result should render");
    assert.equal(postBodies.length, 2);
    assert.equal(postBodies[1].query_type, "TIME_SERIES");
    assert.equal(postBodies[1].group_by, "1h", "TIME_SERIES request must include group_by=1h");
  } finally {
    globalThis.fetch = realFetch;
  }
});

test("POST /tasks failure shows create-failure state without lifecycle expansion or polling", async () => {
  setupDom();
  const realFetch = globalThis.fetch;
  let taskStatusCalls = 0;
  globalThis.fetch = withAuth(async (url, options = {}) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    const json = (data, status = 200) =>
      new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
    if (path.startsWith("/api/v1/privacy/budgets")) {
      return json({ total_epsilon: 20, used_epsilon: 0, remaining_epsilon: 20 });
    }
    if (options.method === "POST" && path === "/api/v1/tasks") {
      return json({ detail: "insufficient privacy budget" }, 409);
    }
    if (path.startsWith("/api/v1/tasks/")) {
      taskStatusCalls += 1;
      return json({ detail: "must not be polled" }, 404);
    }
    return json({ detail: `unexpected request ${path}` }, 404);
  });

  try {
    await import(`../src/main.js?failflow=${Date.now()}`);
    await loginToPlatform();
    click('[data-page="query"]');
    await settle();
    click("#q-submit");
    await settle(300);

    const resultText = document.querySelector("#q-result")?.textContent || "";
    assert.ok(resultText.includes("insufficient privacy budget"), "failure detail should be shown");
    const stepsText = document.querySelector("#q-steps")?.textContent || "";
    assert.ok(stepsText.includes("创建失败"), "lifecycle should show create-failure");
    assert.ok(!stepsText.includes("园区本地计算"), "later stages must not expand on POST failure");
    assert.ok(!stepsText.includes("秘密共享"), "later stages must not expand on POST failure");
    assert.ok(!stepsText.includes("节点聚合"), "later stages must not expand on POST failure");
    await settle(300);
    assert.equal(taskStatusCalls, 0, "polling must not start when POST /tasks fails");
  } finally {
    globalThis.fetch = realFetch;
  }
});

test("live backend SUM + TIME_SERIES flows work end-to-end (opt-in RUN_LIVE_E2E=1)", async (t) => {
  if (process.env.RUN_LIVE_E2E !== "1") {
    t.skip("RUN_LIVE_E2E not set; skipping live queries against running backend");
    return;
  }
  setupDom();
  await import(`../src/main.js?smoke3=${Date.now()}`);
  await loginToPlatform();
  click('[data-page="query"]');
  await settle();

  // 任务一：SUM（默认表单即 SUM，且时间粒度控件隐藏）
  click("#q-submit");
  let sumDone = false;
  for (let i = 0; i < 45; i++) {
    await settle(1000);
    const text = document.querySelector("#q-result")?.textContent || "";
    const error = document.querySelector("#q-result .api-state.error")?.textContent || "";
    if (error) {
      assert.fail(`live query failed: ${error}`);
    }
    if (text.includes("kWh（带噪总用电量）")) {
      sumDone = true;
      break;
    }
  }
  assert.ok(sumDone, "live SUM result should render within 45s");
  assert.ok((document.querySelector("#q-status")?.textContent || "").includes("TASK-"));

  // 任务二：TIME_SERIES 1h，同一天范围，验证 24 桶与峰谷指标
  const typeSelect = document.querySelector("#q-type");
  typeSelect.value = "TIME_SERIES";
  typeSelect.dispatchEvent(new Event("change", { bubbles: true }));
  const groupSelect = document.querySelector("#q-group");
  assert.equal(groupSelect.disabled, false);
  assert.equal(groupSelect.value, "1h");
  click("#q-submit");

  let tsDone = false;
  for (let i = 0; i < 45; i++) {
    await settle(1000);
    const text = document.querySelector("#q-result")?.textContent || "";
    const error = document.querySelector("#q-result .api-state.error")?.textContent || "";
    if (error) {
      assert.fail(`live TIME_SERIES query failed: ${error}`);
    }
    if (text.includes("时间桶数量") && text.includes("峰值负荷")) {
      tsDone = true;
      break;
    }
  }
  assert.ok(tsDone, "live TIME_SERIES result should show bucket metrics within 45s");
  assert.ok((document.querySelector("#q-result")?.textContent || "").includes("24"), "TIME_SERIES should return 24 buckets");
});
