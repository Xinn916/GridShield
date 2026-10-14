import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { JSDOM } from "jsdom";

process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://127.0.0.1:8000";

const user = { user_id: "analyst_demo", username: "analyst_demo", role: "ANALYST", party_id: null, is_active: true };
const grant = {
  grant_id: "GRANT-INTENT",
  request_id: "REQUEST-INTENT",
  grantee_user_id: "analyst_demo",
  parties: ["ORG_A", "ORG_B", "ORG_C"],
  allowed_query_types: ["SUM", "COUNT", "AVERAGE", "TIME_SERIES"],
  allowed_start_time: "2012-11-11T00:00:00",
  allowed_end_time: "2012-11-12T00:00:00",
  allowed_group_by: ["30m", "1h", "1d"],
  max_epsilon_per_query: 5,
  total_epsilon_limit: 20,
  epsilon_consumed: 2,
  epsilon_reserved: 0,
  epsilon_remaining: 18,
  valid_from: "2012-01-01T00:00:00",
  expires_at: "2099-01-01T00:00:00",
  status: "ACTIVE",
  created_at: "2012-01-01T00:00:00",
  revoked_at: null,
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

function setupDom() {
  const dom = new JSDOM("<!doctype html><html><body><div id='app'></div></body></html>", {
    url: "http://localhost:5173/",
    pretendToBeVisual: true,
  });
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.HTMLElement = dom.window.HTMLElement;
  globalThis.Element = dom.window.Element;
  globalThis.Node = dom.window.Node;
  globalThis.MouseEvent = dom.window.MouseEvent;
  globalThis.Event = dom.window.Event;
}

function click(selector) {
  const element = document.querySelector(selector);
  assert.ok(element, `element not found: ${selector}`);
  element.dispatchEvent(new MouseEvent("click", { bubbles: true }));
}

async function settle(ms = 100) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

function taskFormSnapshot() {
  return {
    type: document.querySelector("#q-type")?.value,
    parties: Array.from(document.querySelectorAll("#q-parties input:checked")).map((item) => item.value),
    start: document.querySelector("#q-start")?.value,
    end: document.querySelector("#q-end")?.value,
    epsilon: document.querySelector("#q-epsilon")?.value,
    group: document.querySelector("#q-group")?.value,
  };
}

async function send(text) {
  document.querySelector("#query-input").value = text;
  click('[data-action="send-query"]');
  await settle(140);
}

async function loginAndOpenQuery(importTag) {
  await import(`../src/main.js?${importTag}=${Date.now()}-${Math.random()}`);
  document.querySelector("#login-username").value = "analyst_demo";
  document.querySelector("#login-password").value = "password";
  document.querySelector("#login-form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await settle(120);
  click('[data-page="query"]');
  await settle(160);
}

test("chat intents keep ordinary conversation separate from multi-turn task updates", async () => {
  setupDom();
  const originalFetch = globalThis.fetch;
  let loggedIn = false;
  let taskPosts = 0;
  const parseBodies = [];
  globalThis.fetch = async (url, options = {}) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    if (path === "/api/v1/auth/me") return json(loggedIn ? user : { detail: "not logged in" }, loggedIn ? 200 : 401);
    if (path === "/api/v1/auth/login") { loggedIn = true; return json(user); }
    if (path === "/api/v1/grants/mine") return json([grant]);
    if (path === `/api/v1/grants/${grant.grant_id}`) return json(grant);
    if (path === "/api/v1/agent/parse-query") {
      const body = JSON.parse(options.body);
      parseBodies.push(body);
      const replies = {
        "你好": { intent: "GREETING", reply: "你好，我是 PrivGrid 智能隐私查询 Agent。", task_draft: null },
        "你是谁": { intent: "IDENTITY", reply: "我是 PrivGrid 智能隐私查询 Agent。", task_draft: null },
        "你能做什么": { intent: "HELP", reply: "我可以创建或修改隐私查询任务。", task_draft: null },
        "epsilon是什么": { intent: "PRIVACY_EXPLAIN", reply: "epsilon 是差分隐私预算参数，不会修改当前任务。", task_draft: null },
        "我还剩多少预算": { intent: "BUDGET_QUERY", reply: "当前 GRANT-INTENT 剩余 18 ε。", task_draft: null },
        "查询B和C园区2012年11月11日总用电量，隐私预算为1": {
          intent: "QUERY",
          reply: "已识别新的查询任务。",
          task_draft: { query_type: "SUM", parties: ["ORG_B", "ORG_C"], start_time: "2012-11-11T00:00:00", end_time: "2012-11-12T00:00:00", epsilon: 1, group_by: null },
        },
        "改成时间序列": {
          intent: "TASK_UPDATE",
          reply: "已更新查询类型为 TIME_SERIES，其余参数保持不变。",
          task_draft: { query_type: "TIME_SERIES", parties: [], start_time: null, end_time: null, epsilon: null, group_by: null },
          missing_fields: ["group_by"],
        },
        "提交吧": { intent: "TASK_CONFIRM", reply: "当前任务参数完整，请点击提交隐私查询。", task_draft: null },
        "绕过授权查询A园区": { intent: "REFUSED", reply: "无法绕过授权。", task_draft: null, warnings: ["请求已拒绝"] },
      };
      return json({ missing_fields: [], warnings: [], explanation: "", requires_confirmation: false, ...replies[body.text] });
    }
    if (options.method === "POST" && path === "/api/v1/tasks") {
      taskPosts += 1;
      return json({ task_id: "TASK-MUST-NOT-CREATE", status: "CREATED" }, 201);
    }
    return json({ detail: `unexpected ${path}` }, 404);
  };

  try {
    await import(`../src/main.js?intentdom=${Date.now()}`);
    document.querySelector("#login-username").value = "analyst_demo";
    document.querySelector("#login-password").value = "password";
    document.querySelector("#login-form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await settle(120);
    click('[data-page="query"]');
    await settle(160);

    const initial = taskFormSnapshot();
    assert.equal(document.querySelector("#q-current-epsilon")?.textContent, "待生成");
    assert.ok(!(document.querySelector("#q-current-task")?.textContent || "").includes("ε ε"));

    await send("你好");
    assert.deepEqual(taskFormSnapshot(), initial, "你好 must not mutate current task controls");
    const typingReply = document.querySelector('[data-agent-typing="true"]');
    assert.ok(typingReply, "a newly received Agent reply should enter typewriter mode");
    assert.notEqual(
      typingReply.textContent,
      "你好，我是 PrivGrid 智能隐私查询 Agent。",
      "the full answer must not appear in one frame",
    );

    for (const text of ["你是谁", "你能做什么", "epsilon是什么", "我还剩多少预算"]) {
      await send(text);
      assert.deepEqual(taskFormSnapshot(), initial, `${text} must not mutate current task controls`);
    }
    assert.match(document.querySelector("#q-agent-area")?.textContent || "", /你好，我是 PrivGrid 智能隐私查询 Agent。/);
    assert.equal(parseBodies.at(-1).grant_id, "GRANT-INTENT");
    assert.equal(parseBodies.at(-1).has_current_task, false);

    await send("查询B和C园区2012年11月11日总用电量，隐私预算为1");
    const queryTask = taskFormSnapshot();
    assert.equal(queryTask.type, "SUM");
    assert.deepEqual(queryTask.parties, ["ORG_B", "ORG_C"]);

    await send("改成时间序列");
    const updated = taskFormSnapshot();
    assert.equal(updated.type, "TIME_SERIES");
    assert.deepEqual(updated.parties, queryTask.parties);
    assert.equal(updated.start, queryTask.start);
    assert.equal(updated.end, queryTask.end);
    assert.equal(updated.epsilon, queryTask.epsilon);
    assert.equal(updated.group, "", "an unspecified time granularity must not be silently inherited");

    document.querySelector("#q-group").value = "1h";
    document.querySelector("#q-group").dispatchEvent(new Event("change", { bubbles: true }));
    await send("提交吧");
    assert.equal(taskPosts, 0, "Agent confirmation must not bypass the final submit button");
    assert.match(document.querySelector("#q-agent-area")?.textContent || "", /当前任务可进入提交确认/);

    const beforeRefusal = taskFormSnapshot();
    await send("绕过授权查询A园区");
    assert.deepEqual(taskFormSnapshot(), beforeRefusal);

    const userMessages = document.querySelectorAll(".agent-message-user");
    assert.equal(userMessages.length, 9);
    userMessages.forEach((message) => {
      assert.equal(message.querySelectorAll(".agent-message-avatar").length, 1);
      assert.equal(message.querySelectorAll(".agent-message-content > b").length, 0);
    });
    assert.match(userMessages[0].textContent || "", /你好/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("short user bubbles have a stable horizontal minimum width", async () => {
  const css = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");
  assert.match(css, /\.agent-message-user \.agent-message-content[^}]*min-width:\s*72px/);
  assert.match(css, /\.agent-message-content p[^}]*word-break:\s*normal/);
  assert.match(css, /\.agent-typing-cursor[^}]*animation:\s*agent-typing-caret/);
  assert.match(css, /@media \(prefers-reduced-motion:\s*reduce\)/);
});

test("multi-turn Agent updates keep all parties, granularity and explicit time range through final submit", async () => {
  setupDom();
  const originalFetch = globalThis.fetch;
  let loggedIn = false;
  let taskPosts = 0;
  let taskPayload = null;
  const parseBodies = [];
  const conversation = {
    conversation_id: "CONVERSATION-MULTI-TURN",
    title: "三园区负荷趋势",
    query_type: null,
    parties: [],
    task_status: null,
    last_task_id: null,
    has_current_task: false,
    created_at: "2026-09-08T10:00:00",
    updated_at: "2026-09-08T10:00:00",
  };

  globalThis.fetch = async (url, options = {}) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    if (path === "/api/v1/auth/me") return json(loggedIn ? user : { detail: "not logged in" }, loggedIn ? 200 : 401);
    if (path === "/api/v1/auth/login") { loggedIn = true; return json(user); }
    if (path === "/api/v1/grants/mine") return json([grant]);
    if (path === `/api/v1/grants/${grant.grant_id}`) return json(grant);
    if (path === "/api/v1/agent/conversations?limit=50") return json([]);
    if (path === "/api/v1/agent/conversations" && options.method === "POST") return json(conversation, 201);
    if (path.startsWith(`/api/v1/agent/conversations/${conversation.conversation_id}/tasks/`) && options.method === "POST") {
      return json({ ...conversation, last_task_id: "TASK-MULTI-TURN", has_current_task: true });
    }
    if (path === "/api/v1/agent/parse-query") {
      const body = JSON.parse(options.body);
      parseBodies.push(body);
      const replies = {
        "查询三个园区的小时负荷趋势": {
          intent: "QUERY",
          reply: "已识别三园区小时负荷趋势任务。",
          task_draft: {
            query_type: "TIME_SERIES",
            parties: ["ORG_A", "ORG_B", "ORG_C"],
            start_time: "2012-11-11T00:00:00",
            end_time: "2012-11-12T00:00:00",
            epsilon: 1,
            group_by: "1h",
          },
        },
        "时间粒度为30分钟": {
          intent: "TASK_UPDATE",
          reply: "时间粒度已更新为 30 分钟。",
          task_draft: { query_type: null, parties: [], start_time: null, end_time: null, epsilon: null, group_by: "30m" },
        },
        "时间粒度为1天": {
          intent: "TASK_UPDATE",
          reply: "时间粒度已更新为 1 天。",
          task_draft: { query_type: null, parties: [], start_time: null, end_time: null, epsilon: null, group_by: "1d" },
        },
        "时间范围改为2012年11月11日06:00到18:00": {
          intent: "TASK_UPDATE",
          reply: "查询时间范围已更新。",
          task_draft: {
            query_type: null,
            parties: [],
            start_time: "2012-11-11T06:00:00",
            end_time: "2012-11-11T18:00:00",
            epsilon: null,
            group_by: null,
          },
        },
        "确认执行": { intent: "TASK_CONFIRM", reply: "当前任务参数完整，请点击提交隐私查询。", task_draft: null },
      };
      return json({
        missing_fields: [],
        warnings: [],
        explanation: "",
        requires_confirmation: true,
        ...replies[body.text],
      });
    }
    if (path === "/api/v1/tasks" && options.method === "POST") {
      taskPosts += 1;
      taskPayload = JSON.parse(options.body);
      return json({
        task_id: "TASK-MULTI-TURN",
        status: "CREATED",
        query_type: taskPayload.query_type,
        parties: taskPayload.parties,
        epsilon: taskPayload.epsilon,
        calculation_mode: "DISTRIBUTED_DP",
      }, 201);
    }
    if (path === "/api/v1/tasks/TASK-MULTI-TURN") {
      return json({
        task_id: "TASK-MULTI-TURN",
        status: "COMPLETED",
        query_type: "TIME_SERIES",
        parties: ["ORG_A", "ORG_B", "ORG_C"],
        epsilon: 1,
        calculation_mode: "DISTRIBUTED_DP",
        duration_ms: 80,
      });
    }
    if (path === "/api/v1/tasks/TASK-MULTI-TURN/result") {
      return json({ task_id: "TASK-MULTI-TURN", status: "COMPLETED", query_type: "TIME_SERIES", result: { buckets: [] } });
    }
    if (path.startsWith("/api/v1/privacy/budgets")) {
      return json({ total_epsilon: 20, used_epsilon: 3, remaining_epsilon: 17 });
    }
    return json({ detail: `unexpected ${path}` }, 404);
  };

  try {
    await loginAndOpenQuery("agentmultiturn");

    await send("查询三个园区的小时负荷趋势");
    assert.deepEqual(taskFormSnapshot(), {
      type: "TIME_SERIES",
      parties: ["ORG_A", "ORG_B", "ORG_C"],
      start: "2012-11-11T00:00",
      end: "2012-11-12T00:00",
      epsilon: "1",
      group: "1h",
    });

    await send("时间粒度为30分钟");
    assert.deepEqual(parseBodies[1].current_form, {
      query_type: "TIME_SERIES",
      parties: ["ORG_A", "ORG_B", "ORG_C"],
      start_time: "2012-11-11T00:00",
      end_time: "2012-11-12T00:00",
      epsilon: 1,
      group_by: "1h",
    });
    assert.equal(taskFormSnapshot().group, "30m");

    await send("时间粒度为1天");
    assert.equal(parseBodies[2].current_form.group_by, "30m", "the next turn must receive the previous 30m update");
    assert.equal(taskFormSnapshot().group, "1d");

    const beforeTimeUpdate = taskFormSnapshot();
    await send("时间范围改为2012年11月11日06:00到18:00");
    const afterTimeUpdate = taskFormSnapshot();
    assert.equal(parseBodies[3].current_form.group_by, "1d");
    assert.equal(afterTimeUpdate.start, "2012-11-11T06:00");
    assert.equal(afterTimeUpdate.end, "2012-11-11T18:00");
    assert.equal(afterTimeUpdate.type, beforeTimeUpdate.type);
    assert.deepEqual(afterTimeUpdate.parties, beforeTimeUpdate.parties);
    assert.equal(afterTimeUpdate.epsilon, beforeTimeUpdate.epsilon);
    assert.equal(afterTimeUpdate.group, beforeTimeUpdate.group);

    await send("确认执行");
    assert.equal(parseBodies[4].current_form.start_time, "2012-11-11T06:00");
    assert.equal(parseBodies[4].current_form.end_time, "2012-11-11T18:00");
    assert.equal(parseBodies[4].current_form.group_by, "1d");
    assert.equal(taskPosts, 0, "Agent confirmation must never create the task by itself");
    assert.equal(document.querySelector("#q-submit").disabled, false);

    click("#q-submit");
    await settle(100);
    assert.equal(taskPosts, 1);
    assert.deepEqual(taskPayload, {
      grant_id: grant.grant_id,
      query_type: "TIME_SERIES",
      parties: ["ORG_A", "ORG_B", "ORG_C"],
      start_time: "2012-11-11T06:00:00",
      end_time: "2012-11-11T18:00:00",
      epsilon: 1,
      group_by: "1d",
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("a missing-granularity task keeps its full context when the next turn supplies 30 minutes", async () => {
  setupDom();
  const originalFetch = globalThis.fetch;
  let loggedIn = false;
  let taskPayload = null;
  const parseBodies = [];

  globalThis.fetch = async (url, options = {}) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    if (path === "/api/v1/auth/me") return json(loggedIn ? user : { detail: "not logged in" }, loggedIn ? 200 : 401);
    if (path === "/api/v1/auth/login") { loggedIn = true; return json(user); }
    if (path === "/api/v1/grants/mine") return json([grant]);
    if (path === `/api/v1/grants/${grant.grant_id}`) return json(grant);
    if (path === "/api/v1/agent/conversations?limit=50") return json([]);
    if (path === "/api/v1/agent/conversations" && options.method === "POST") {
      return json({
        conversation_id: "CONVERSATION-MISSING-GROUP",
        title: "三园区时间序列",
        parties: [],
        has_current_task: false,
        created_at: "2026-09-08T10:00:00",
        updated_at: "2026-09-08T10:00:00",
      }, 201);
    }
    if (path === "/api/v1/agent/parse-query") {
      const body = JSON.parse(options.body);
      parseBodies.push(body);
      if (body.text === "查询三园区时间序列") {
        return json({
          intent: "QUERY",
          reply: "已识别三园区时间序列，请补充时间粒度。",
          task_draft: {
            query_type: "TIME_SERIES",
            parties: ["ORG_A", "ORG_B", "ORG_C"],
            start_time: "2012-11-11T00:00:00",
            end_time: "2012-11-12T00:00:00",
            epsilon: 1,
            group_by: null,
          },
          missing_fields: ["group_by"],
          warnings: [],
          explanation: "",
          requires_confirmation: true,
        });
      }
      if (body.text === "时间粒度30分钟就行") {
        return json({
          intent: "TASK_UPDATE",
          reply: "时间粒度已更新为 30 分钟，其余条件保持不变。",
          task_draft: {
            query_type: null,
            parties: [],
            start_time: null,
            end_time: null,
            epsilon: null,
            group_by: "30m",
          },
          missing_fields: [],
          warnings: [],
          explanation: "",
          requires_confirmation: true,
        });
      }
      return json({ detail: `unexpected Agent text: ${body.text}` }, 400);
    }
    if (path === "/api/v1/tasks" && options.method === "POST") {
      taskPayload = JSON.parse(options.body);
      return json({
        task_id: "TASK-MISSING-GROUP",
        status: "CREATED",
        query_type: taskPayload.query_type,
        parties: taskPayload.parties,
        epsilon: taskPayload.epsilon,
        calculation_mode: "DISTRIBUTED_DP",
      }, 201);
    }
    if (path === "/api/v1/tasks/TASK-MISSING-GROUP") {
      return json({
        task_id: "TASK-MISSING-GROUP",
        status: "COMPLETED",
        query_type: "TIME_SERIES",
        parties: ["ORG_A", "ORG_B", "ORG_C"],
        epsilon: 1,
        calculation_mode: "DISTRIBUTED_DP",
        duration_ms: 80,
      });
    }
    if (path === "/api/v1/tasks/TASK-MISSING-GROUP/result") {
      return json({ task_id: "TASK-MISSING-GROUP", status: "COMPLETED", query_type: "TIME_SERIES", result: { buckets: [] } });
    }
    if (path.startsWith("/api/v1/privacy/budgets")) {
      return json({ total_epsilon: 20, used_epsilon: 3, remaining_epsilon: 17 });
    }
    return json({ detail: `unexpected ${path}` }, 404);
  };

  try {
    await loginAndOpenQuery("agentmissinggroupcontext");

    await send("查询三园区时间序列");
    assert.deepEqual(taskFormSnapshot(), {
      type: "TIME_SERIES",
      parties: ["ORG_A", "ORG_B", "ORG_C"],
      start: "2012-11-11T00:00",
      end: "2012-11-12T00:00",
      epsilon: "1",
      group: "",
    });
    assert.equal(document.querySelector("#q-submit").disabled, false, "validation blockers must keep the submit control clickable");
    assert.equal(document.querySelector("#q-submit").getAttribute("aria-disabled"), "true", "the incomplete first turn must remain blocked");

    await send("时间粒度30分钟就行");
    assert.equal(parseBodies[1].has_current_task, true, "the follow-up must be marked as an update to an existing task");
    assert.deepEqual(parseBodies[1].current_form, {
      query_type: "TIME_SERIES",
      parties: ["ORG_A", "ORG_B", "ORG_C"],
      start_time: "2012-11-11T00:00",
      end_time: "2012-11-12T00:00",
      epsilon: 1,
      group_by: null,
    }, "the second request must carry all fields recognized on the first turn");
    assert.deepEqual(taskFormSnapshot(), {
      type: "TIME_SERIES",
      parties: ["ORG_A", "ORG_B", "ORG_C"],
      start: "2012-11-11T00:00",
      end: "2012-11-12T00:00",
      epsilon: "1",
      group: "30m",
    });
    assert.equal(document.querySelector("#q-submit").disabled, false, "an authorized complete update must become submittable");

    click("#q-submit");
    await settle(100);
    assert.deepEqual(taskPayload, {
      grant_id: grant.grant_id,
      query_type: "TIME_SERIES",
      parties: ["ORG_A", "ORG_B", "ORG_C"],
      start_time: "2012-11-11T00:00:00",
      end_time: "2012-11-12T00:00:00",
      epsilon: 1,
      group_by: "30m",
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("native time granularity stays editable across history renders and gates submission when missing", async () => {
  setupDom();
  const originalFetch = globalThis.fetch;
  let loggedIn = false;
  let taskPosts = 0;
  globalThis.fetch = async (url, options = {}) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    if (path === "/api/v1/auth/me") return json(loggedIn ? user : { detail: "not logged in" }, loggedIn ? 200 : 401);
    if (path === "/api/v1/auth/login") { loggedIn = true; return json(user); }
    if (path === "/api/v1/grants/mine") return json([grant]);
    if (path === `/api/v1/grants/${grant.grant_id}`) return json(grant);
    if (path === "/api/v1/agent/conversations?limit=50") return json([]);
    if (path === "/api/v1/agent/conversations" && options.method === "POST") {
      return json({
        conversation_id: "CONVERSATION-GROUP",
        title: "粒度回归",
        parties: [],
        has_current_task: false,
        created_at: "2026-09-08T10:00:00",
        updated_at: "2026-09-08T10:00:00",
      }, 201);
    }
    if (path === "/api/v1/agent/parse-query") {
      return json({
        intent: "QUERY",
        reply: "请选择时间粒度。",
        task_draft: {
          query_type: "TIME_SERIES",
          parties: ["ORG_A", "ORG_B", "ORG_C"],
          start_time: "2012-11-11T00:00:00",
          end_time: "2012-11-12T00:00:00",
          epsilon: 1,
          group_by: null,
        },
        missing_fields: ["group_by"],
        warnings: [],
        explanation: "",
        requires_confirmation: true,
      });
    }
    if (path === "/api/v1/tasks" && options.method === "POST") {
      taskPosts += 1;
      return json({ task_id: "TASK-UNEXPECTED", status: "CREATED" }, 201);
    }
    return json({ detail: `unexpected ${path}` }, 404);
  };

  try {
    await loginAndOpenQuery("agentgroupselect");
    await send("查询三个园区的负荷趋势");

    const group = document.querySelector("#q-group");
    assert.equal(group.value, "");
    assert.equal(group.disabled, false, "TIME_SERIES granularity must remain editable");
    assert.equal(document.querySelector("#q-submit").disabled, false, "missing group_by must keep the submit control clickable");
    assert.equal(document.querySelector("#q-submit").getAttribute("aria-disabled"), "true", "missing group_by must block submission");

    group.value = "30m";
    group.dispatchEvent(new Event("change", { bubbles: true }));
    assert.equal(document.querySelector("#q-submit").disabled, false, "an allowed native selection must enable submission");

    click('[data-action="open-agent-history"]');
    await settle(180);
    assert.equal(document.querySelector("#q-group").value, "30m", "full history-drawer renders must preserve native 30m selection");
    click('[data-action="close-agent-history"]');
    await settle(40);
    assert.equal(document.querySelector("#q-group").value, "30m");

    document.querySelector("#q-group").value = "1d";
    document.querySelector("#q-group").dispatchEvent(new Event("change", { bubbles: true }));
    click('[data-action="open-agent-history"]');
    await settle(180);
    assert.equal(document.querySelector("#q-group").value, "1d", "full history-drawer renders must preserve native 1d selection");
    assert.equal(document.querySelector("#q-submit").disabled, false);
    assert.equal(taskPosts, 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("Agent warns when 30-minute granularity is outside a one-hour Grant and blocks posting", async () => {
  setupDom();
  const originalFetch = globalThis.fetch;
  let loggedIn = false;
  let taskPosts = 0;
  const restrictedGrant = {
    ...grant,
    grant_id: "GRANT-RESTRICTED",
    parties: ["ORG_A"],
    allowed_query_types: ["TIME_SERIES"],
    allowed_group_by: ["1h"],
  };
  globalThis.fetch = async (url, options = {}) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    if (path === "/api/v1/auth/me") return json(loggedIn ? user : { detail: "not logged in" }, loggedIn ? 200 : 401);
    if (path === "/api/v1/auth/login") { loggedIn = true; return json(user); }
    if (path === "/api/v1/grants/mine") return json([restrictedGrant]);
    if (path === `/api/v1/grants/${restrictedGrant.grant_id}`) return json(restrictedGrant);
    if (path === "/api/v1/agent/conversations?limit=50") return json([]);
    if (path === "/api/v1/agent/conversations" && options.method === "POST") {
      return json({
        conversation_id: "CONVERSATION-RESTRICTED",
        title: "越权回归",
        parties: [],
        has_current_task: false,
        created_at: "2026-09-08T10:00:00",
        updated_at: "2026-09-08T10:00:00",
      }, 201);
    }
    if (path === "/api/v1/agent/parse-query") {
      return json({
        intent: "QUERY",
        reply: "已识别任务，请核验授权范围。",
        task_draft: {
          query_type: "TIME_SERIES",
          parties: ["ORG_A"],
          start_time: "2012-11-11T00:00:00",
          end_time: "2012-11-12T00:00:00",
          epsilon: 1,
          group_by: "30m",
        },
        missing_fields: [],
        warnings: [],
        explanation: "",
        requires_confirmation: true,
      });
    }
    if (path === "/api/v1/tasks" && options.method === "POST") {
      taskPosts += 1;
      return json({ task_id: "TASK-MUST-NOT-CREATE", status: "CREATED" }, 201);
    }
    return json({ detail: `unexpected ${path}` }, 404);
  };

  try {
    await loginAndOpenQuery("agentgrantblock");
    await send("查询ORG_A每30分钟负荷");

    const area = document.querySelector("#q-agent-area")?.textContent || "";
    assert.match(area, /授权提示/);
    assert.match(area, /30 分钟/);
    assert.match(area, /1 小时/);
    assert.match(area, /需要补充或调整参数/);
    assert.equal(document.querySelector("#q-grant").value, restrictedGrant.grant_id, "Agent must not silently switch Grants");
    const hint = document.querySelector("#q-submit-hint");
    assert.ok(hint, "an authorization blocker must be rendered beside the submit action");
    assert.match(hint.textContent || "", /30 分钟/);
    assert.match(hint.textContent || "", /1 小时/);
    const submit = document.querySelector("#q-submit");
    assert.equal(submit.disabled, false, "an invalid task must keep the submit control clickable so it can explain the blocker");
    assert.equal(submit.getAttribute("aria-disabled"), "true", "an unauthorized draft must not be submittable");

    click("#q-submit");
    await settle(80);
    assert.equal(taskPosts, 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("submit explains a missing party, focuses the allowed party, and recovers after reselection", async () => {
  setupDom();
  const originalFetch = globalThis.fetch;
  let loggedIn = false;
  let taskPosts = 0;
  const restrictedGrant = {
    ...grant,
    grant_id: "GRANT-PARTY-REQUIRED",
    parties: ["ORG_A"],
    allowed_query_types: ["TIME_SERIES"],
    allowed_group_by: ["1h"],
  };
  globalThis.fetch = async (url, options = {}) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    if (path === "/api/v1/auth/me") return json(loggedIn ? user : { detail: "not logged in" }, loggedIn ? 200 : 401);
    if (path === "/api/v1/auth/login") { loggedIn = true; return json(user); }
    if (path === "/api/v1/grants/mine") return json([restrictedGrant]);
    if (path === `/api/v1/grants/${restrictedGrant.grant_id}`) return json(restrictedGrant);
    if (path === "/api/v1/agent/conversations?limit=50") return json([]);
    if (path === "/api/v1/agent/conversations" && options.method === "POST") {
      return json({
        conversation_id: "CONVERSATION-PARTY-REQUIRED",
        title: "园区必选回归",
        parties: [],
        has_current_task: false,
        created_at: "2026-09-09T10:00:00",
        updated_at: "2026-09-09T10:00:00",
      }, 201);
    }
    if (path === "/api/v1/agent/parse-query") {
      return json({
        intent: "QUERY",
        reply: "已生成当前授权范围内的小时负荷任务。",
        task_draft: {
          query_type: "TIME_SERIES",
          parties: ["ORG_A"],
          start_time: "2012-11-11T00:00:00",
          end_time: "2012-11-12T00:00:00",
          epsilon: 1,
          group_by: "1h",
        },
        missing_fields: [],
        warnings: [],
        explanation: "",
        requires_confirmation: true,
      });
    }
    if (path === "/api/v1/tasks" && options.method === "POST") {
      taskPosts += 1;
      return json({
        task_id: "TASK-PARTY-READY",
        status: "CREATED",
        query_type: "TIME_SERIES",
        parties: ["ORG_A"],
        epsilon: 1,
      }, 201);
    }
    if (path === "/api/v1/tasks/TASK-PARTY-READY") {
      return json({ task_id: "TASK-PARTY-READY", status: "FAILED", error: "test stop" });
    }
    if (path === "/api/v1/agent/conversations/CONVERSATION-PARTY-REQUIRED/tasks/TASK-PARTY-READY" && options.method === "POST") {
      return json({
        conversation_id: "CONVERSATION-PARTY-REQUIRED",
        title: "园区必选回归",
        parties: ["ORG_A"],
        has_current_task: true,
        last_task_id: "TASK-PARTY-READY",
        created_at: "2026-09-09T10:00:00",
        updated_at: "2026-09-09T10:01:00",
      });
    }
    return json({ detail: `unexpected ${path}` }, 404);
  };

  try {
    await loginAndOpenQuery("agentpartyrequired");
    await send("查询ORG_A小时负荷");

    const orgA = document.querySelector('#q-parties input[value="ORG_A"]');
    const submit = document.querySelector("#q-submit");
    const hint = document.querySelector("#q-submit-hint");
    assert.ok(orgA && submit && hint);
    assert.equal(submit.disabled, false);
    assert.equal(submit.getAttribute("aria-disabled"), "false");

    orgA.checked = false;
    orgA.dispatchEvent(new Event("change", { bubbles: true }));

    assert.match(hint.textContent || "", /至少选择一个园区/);
    assert.match(hint.textContent || "", /ORG_A/);
    assert.equal(submit.disabled, false, "a correctable blocker must keep the submit control clickable");
    assert.equal(submit.getAttribute("aria-disabled"), "true");

    click("#q-submit");
    await settle(40);
    assert.equal(taskPosts, 0, "clicking a blocked submit must never call the task API");
    assert.equal(document.activeElement, orgA, "the blocker action should focus the selectable authorized party");

    orgA.checked = true;
    orgA.dispatchEvent(new Event("change", { bubbles: true }));
    assert.ok(hint.hidden || !(hint.textContent || "").trim(), "the party hint must clear after the task becomes valid");
    assert.equal(submit.getAttribute("aria-disabled"), "false");

    click("#q-submit");
    await settle(80);
    assert.equal(taskPosts, 1, "a corrected task must be posted exactly once");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
