import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "jsdom";

process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://127.0.0.1:8000";

const user = { user_id: "analyst_demo", username: "analyst_demo", role: "ANALYST", party_id: null, is_active: true };
const grant = {
  grant_id: "GRANT-WORKBENCH",
  request_id: "REQUEST-WORKBENCH",
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

class FakeSpeechRecognition {
  static instances = [];

  constructor() {
    this.startCalls = 0;
    this.stopCalls = 0;
    FakeSpeechRecognition.instances.push(this);
  }

  start() {
    this.startCalls += 1;
    this.onstart?.();
  }

  stop() {
    this.stopCalls += 1;
  }

  abort() {}

  emit(items) {
    const results = items.map(({ text, final = false }) => {
      const result = [{ transcript: text }];
      result.isFinal = final;
      return result;
    });
    this.onresult?.({ results });
  }
}

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
  dom.window.webkitSpeechRecognition = FakeSpeechRecognition;
  return dom;
}

function click(selector) {
  const element = document.querySelector(selector);
  assert.ok(element, `element not found: ${selector}`);
  element.dispatchEvent(new MouseEvent("click", { bubbles: true }));
}

async function settle(ms = 100) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

test("authorization query renders an Agent-first workbench with collapsed parameters and result tabs", async () => {
  setupDom();
  const originalFetch = globalThis.fetch;
  let loggedIn = false;
  let parseCalls = 0;
  globalThis.fetch = async (url) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    if (path === "/api/v1/auth/me") return json(loggedIn ? user : { detail: "not logged in" }, loggedIn ? 200 : 401);
    if (path === "/api/v1/auth/login") { loggedIn = true; return json(user); }
    if (path === "/api/v1/grants/mine") return json([grant]);
    if (path === `/api/v1/grants/${grant.grant_id}`) return json(grant);
    if (path === "/api/v1/agent/parse-query") {
      parseCalls += 1;
      return json({
        intent: "QUERY",
        reply: "请补充查询日期和隐私预算。",
        task_draft: { query_type: "SUM", parties: ["ORG_A", "ORG_B", "ORG_C"], start_time: null, end_time: null, epsilon: null, group_by: null },
        missing_fields: ["start_time", "end_time", "epsilon"],
        warnings: [],
        requires_confirmation: true,
      });
    }
    return json({ detail: `unexpected ${path}` }, 404);
  };

  try {
    await import(`../src/main.js?queryworkbench=${Date.now()}`);
    document.querySelector("#login-username").value = "analyst_demo";
    document.querySelector("#login-password").value = "password";
    document.querySelector("#login-form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await settle(120);
    click('[data-page="query"]');
    await settle(180);

    assert.match(document.querySelector(".query-page-heading")?.textContent || "", /智能隐私查询/);
    assert.match(document.querySelector(".agent-workbench-card")?.textContent || "", /你好，请描述需要分析的能源数据任务/);
    assert.equal(document.querySelectorAll(".agent-workbench-card").length, 1, "Agent and current task must share one outer card");
    assert.ok(document.querySelector(".agent-workbench-card .agent-main-column"));
    assert.ok(document.querySelector(".agent-workbench-card .current-task-column"));
    assert.ok(document.querySelector(".agent-main-column > .agent-conversation"));
    assert.ok(document.querySelector(".agent-main-column > .agent-composer"));
    assert.ok(document.querySelector(".agent-workbench-card").nextElementSibling?.classList.contains("query-lifecycle-card"), "lifecycle must immediately follow the workbench");
    assert.match(document.querySelector("#q-current-task")?.textContent || "", /GRANT-WORKBENCH/);
    assert.equal(document.querySelectorAll("#q-steps .query-progress-step").length, 6);
    assert.equal(document.querySelectorAll(".query-result-tabs [data-action='query-tab']").length, 3);
    assert.equal(document.querySelector("[data-tab='governance']"), null);

    const microphone = document.querySelector('[data-action="toggle-speech-input"]');
    assert.ok(microphone, "supported browsers must show the microphone button");
    assert.equal(microphone.disabled, false);
    assert.equal(microphone.getAttribute("aria-label"), "开始语音输入");
    click('[data-action="toggle-speech-input"]');
    const recognition = FakeSpeechRecognition.instances.at(-1);
    assert.equal(recognition.startCalls, 1);
    assert.equal(microphone.getAttribute("aria-label"), "停止语音输入");
    recognition.emit([{ text: "查询园区", final: false }]);
    recognition.emit([{ text: "查询园区B", final: false }]);
    assert.equal(document.querySelector("#query-input").value, "查询园区B");
    assert.equal(parseCalls, 0, "speech recognition must never auto-send");
    click('[data-action="toggle-speech-input"]');
    assert.equal(recognition.stopCalls, 1);
    recognition.onend?.();
    assert.equal(document.querySelector("#query-input").value, "查询园区B");

    const editor = document.querySelector("#q-param-editor");
    assert.equal(editor.hidden, true, "parameter editor must be collapsed by default");
    click('[data-action="edit-params"][aria-controls="q-param-editor"]');
    assert.equal(editor.hidden, false, "edit parameters must reveal the existing form");

    click('[data-action="query-prompt"][data-prompt="查询三园区总负荷"]');
    await settle(120);
    assert.equal(parseCalls, 1, "recommended questions must use the real Agent entry point");
    assert.match(document.querySelector("#q-agent-area")?.textContent || "", /查询三园区总负荷/);

    click('[data-action="query-tab"][data-tab="logs"]');
    assert.equal(document.querySelector("[data-tab-panel='result']").hidden, true);
    assert.equal(document.querySelector("[data-tab-panel='logs']").hidden, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
