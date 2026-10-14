import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "jsdom";

process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://127.0.0.1:8000";

const user = { user_id: "analyst_demo", username: "analyst_demo", role: "ANALYST", party_id: null, is_active: true };
const grant = {
  grant_id: "GRANT-HISTORY", request_id: "REQUEST-HISTORY", grantee_user_id: "analyst_demo",
  parties: ["ORG_A", "ORG_B", "ORG_C"], allowed_query_types: ["SUM", "COUNT", "AVERAGE", "TIME_SERIES"],
  allowed_start_time: "2012-11-11T00:00:00", allowed_end_time: "2012-11-12T00:00:00",
  allowed_group_by: ["30m", "1h", "1d"], max_epsilon_per_query: 5, total_epsilon_limit: 20,
  epsilon_consumed: 1, epsilon_reserved: 0, epsilon_remaining: 19, valid_from: "2012-01-01T00:00:00",
  expires_at: "2099-01-01T00:00:00", status: "ACTIVE", created_at: "2012-01-01T00:00:00", revoked_at: null,
};

class FakeSpeechRecognition {
  static instances = [];

  constructor() {
    this.startCalls = 0;
    this.stopCalls = 0;
    this.abortCalls = 0;
    FakeSpeechRecognition.instances.push(this);
  }

  start() { this.startCalls += 1; this.onstart?.(); }
  stop() { this.stopCalls += 1; }
  abort() { this.abortCalls += 1; }
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

function setupDom() {
  const dom = new JSDOM("<!doctype html><html><body><div id='app'></div></body></html>", {
    url: "http://localhost:5173/", pretendToBeVisual: true,
  });
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.HTMLElement = dom.window.HTMLElement;
  globalThis.Element = dom.window.Element;
  globalThis.Node = dom.window.Node;
  globalThis.MouseEvent = dom.window.MouseEvent;
  globalThis.Event = dom.window.Event;
  dom.window.SpeechRecognition = FakeSpeechRecognition;
}

function click(selector) {
  const element = document.querySelector(selector);
  assert.ok(element, `element not found: ${selector}`);
  element.dispatchEvent(new MouseEvent("click", { bubbles: true }));
}

async function settle(ms = 120) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

test("Agent conversations support empty history, persistence, new session and read-only restore", async () => {
  setupDom();
  const originalFetch = globalThis.fetch;
  let loggedIn = false;
  let sequence = 0;
  let taskPosts = 0;
  const parseBodies = [];
  const conversations = new Map();
  const now = () => new Date(2026, 7, 26, 16, sequence).toISOString();
  const detail = (id) => conversations.get(id);
  const summary = (item) => ({
    conversation_id: item.conversation_id, title: item.title, query_type: item.query_type,
    parties: item.parties, task_status: item.task_status, last_task_id: item.last_task_id,
    has_current_task: item.has_current_task, created_at: item.created_at, updated_at: item.updated_at,
  });

  globalThis.fetch = async (url, options = {}) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    if (path === "/api/v1/auth/me") return json(loggedIn ? user : { detail: "not logged in" }, loggedIn ? 200 : 401);
    if (path === "/api/v1/auth/login") { loggedIn = true; return json(user); }
    if (path === "/api/v1/grants/mine") return json([grant]);
    if (path === `/api/v1/grants/${grant.grant_id}`) return json(grant);
    if (path.startsWith("/api/v1/agent/conversations?")) {
      return json([...conversations.values()].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).map(summary));
    }
    if (path === "/api/v1/agent/conversations" && options.method === "POST") {
      sequence += 1;
      const id = `conversation-${sequence}`;
      const created = {
        conversation_id: id, title: "新会话", query_type: null, parties: [], task_status: null,
        last_task_id: null, has_current_task: false, current_task_snapshot: null, messages: [],
        created_at: now(), updated_at: now(),
      };
      conversations.set(id, created);
      return json(created, 201);
    }
    if (path === "/api/v1/agent/parse-query") {
      const body = JSON.parse(options.body);
      parseBodies.push(body);
      const item = detail(body.conversation_id);
      const snapshot = {
        grant_id: grant.grant_id, query_type: "SUM", parties: ["ORG_A", "ORG_B", "ORG_C"],
        start_time: "2012-11-11T00:00:00", end_time: "2012-11-12T00:00:00", group_by: null, epsilon: 1,
      };
      item.title = "三园区总用电量查询";
      item.query_type = "SUM";
      item.parties = snapshot.parties;
      item.has_current_task = true;
      item.current_task_snapshot = snapshot;
      item.last_task_id = "TASK-HISTORY";
      item.task_status = "COMPLETED";
      item.updated_at = now();
      item.messages = [
        { message_id: "m-user", role: "USER", content: body.text, intent: null, task_update: null, created_at: now() },
        { message_id: "m-agent", role: "ASSISTANT", content: "已生成三园区总负荷任务。", intent: "QUERY", task_update: snapshot, created_at: now() },
      ];
      return json({
        conversation_id: body.conversation_id, intent: "QUERY", reply: "已生成三园区总负荷任务。",
        task_draft: snapshot, missing_fields: [], warnings: [], requires_confirmation: true,
      });
    }
    const detailMatch = path.match(/^\/api\/v1\/agent\/conversations\/([^/]+)$/);
    if (detailMatch) return json(detail(decodeURIComponent(detailMatch[1])) || { detail: "not found" }, detail(detailMatch[1]) ? 200 : 404);
    if (path === "/api/v1/tasks/TASK-HISTORY") return json({
      task_id: "TASK-HISTORY", grant_id: grant.grant_id, status: "COMPLETED", query_type: "SUM",
      parties: ["ORG_A", "ORG_B", "ORG_C"], start_time: "2012-11-11T00:00:00",
      end_time: "2012-11-12T00:00:00", group_by: null, calculation_mode: "DISTRIBUTED_DP",
      epsilon: 1, privacy_unit: "household", budget_status: "CONSUMED", duration_ms: 125,
    });
    if (path === "/api/v1/tasks/TASK-HISTORY/result") return json({
      task_id: "TASK-HISTORY", status: "COMPLETED", query_type: "SUM",
      calculation_mode: "DISTRIBUTED_DP", result: { value: 42.5 },
    });
    if (path === "/api/v1/tasks" && options.method === "POST") { taskPosts += 1; return json({}, 500); }
    return json({ detail: `unexpected ${path}` }, 404);
  };

  try {
    await import(`../src/main.js?agentconversations=${Date.now()}`);
    document.querySelector("#login-username").value = "analyst_demo";
    document.querySelector("#login-password").value = "password";
    document.querySelector("#login-form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await settle();
    click('[data-page="query"]');
    await settle(180);

    assert.match(document.querySelector(".agent-workbench-head-actions")?.textContent || "", /新建会话.*历史会话/);
    click('[data-action="open-agent-history"]');
    await settle();
    assert.match(document.querySelector(".agent-history-empty")?.textContent || "", /暂无历史会话/);
    click('[data-action="close-agent-history"]');

    click('[data-action="query-prompt"][data-prompt="查询三园区总负荷"]');
    await settle(260);
    assert.equal(parseBodies.length, 1);
    assert.equal(parseBodies[0].conversation_id, "conversation-1");

    click('[data-action="open-agent-history"]');
    await settle();
    assert.match(document.querySelector(".agent-history-item")?.textContent || "", /三园区总用电量查询/);
    assert.match(document.querySelector(".agent-history-item")?.textContent || "", /SUM · 3方/);
    assert.match(document.querySelector(".agent-history-item")?.textContent || "", /已完成/);
    click('[data-action="close-agent-history"]');

    click('[data-action="toggle-speech-input"]');
    const recognitionBeforeNew = FakeSpeechRecognition.instances.at(-1);
    click('[data-action="new-agent-conversation"]');
    await settle(180);
    assert.equal(recognitionBeforeNew.abortCalls, 1, "new conversation must abort active speech recognition");
    assert.equal(document.querySelectorAll("#q-agent-area .agent-message-user").length, 0);
    assert.equal(document.querySelector("#q-current-type")?.textContent, "待生成");
    assert.equal(conversations.size, 2, "new conversation must keep prior history");

    click('[data-action="open-agent-history"]');
    await settle();
    click('[data-action="close-agent-history"]');
    click('[data-action="toggle-speech-input"]');
    const recognitionBeforeRestore = FakeSpeechRecognition.instances.at(-1);
    click('[data-action="open-agent-history"]');
    await settle();
    click('[data-action="open-agent-conversation"][data-id="conversation-1"]');
    await settle(260);
    assert.equal(recognitionBeforeRestore.abortCalls, 1, "switching history must abort active speech recognition");
    assert.match(document.querySelector("#q-agent-area")?.textContent || "", /查询三园区总负荷/);
    assert.equal(document.querySelector("#q-current-type")?.textContent, "SUM");
    assert.match(document.querySelector("#q-status")?.textContent || "", /已完成/);
    assert.match(document.querySelector("#q-result")?.textContent || "", /42.5/);
    assert.equal(taskPosts, 0, "restoring history must never submit a task");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
