import { test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://127.0.0.1:8000";

const owner = { user_id: "owner_a", username: "owner_a", role: "DATA_OWNER", party_id: "ORG_A", is_active: true };
const historyItem = {
  approval_id: "APPROVAL-HISTORY-1",
  request_id: "REQUEST-HISTORY-1",
  party_id: "ORG_A",
  decision: "APPROVED",
  decided_at: "2026-08-10T10:00:00",
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

function setup({ historyFails = false, delayedPendingFailure = false } = {}) {
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

  let releasePending;
  const pendingGate = new Promise((resolve) => { releasePending = resolve; });
  const calls = [];
  globalThis.fetch = async (url) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    calls.push(path);
    if (path === "/api/v1/auth/me") return json(owner);
    if (path === "/api/v1/public/config") return json({ app_env: "development" });
    if (path === "/api/v1/approvals/history") {
      return historyFails ? json({ detail: { reason: "database unavailable" } }, 503) : json([historyItem]);
    }
    if (path === "/api/v1/approvals/pending") {
      if (delayedPendingFailure) await pendingGate;
      return json({ detail: { reason: "pending service unavailable" } }, 503);
    }
    if (path === "/api/v1/system/health") return json({ services: [], checked_at: "2026-08-10T00:00:00" });
    if (path === "/api/v1/parties" || path.startsWith("/api/v1/tasks")) return json([]);
    if (path.startsWith("/api/v1/privacy/budgets")) return json({ total_epsilon: 20, used_epsilon: 0, reserved_epsilon: 0, remaining_epsilon: 20 });
    return json([]);
  };
  return { calls, releasePending };
}

function clickPage(page) {
  const element = document.querySelector(`[data-page="${page}"]`);
  assert.ok(element, `menu entry not found: ${page}`);
  element.dispatchEvent(new MouseEvent("click", { bubbles: true }));
}

async function settle(ms = 160) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

test("approval history renders its successful main list without unsafe error text", async () => {
  const { calls } = setup();
  await import(`../src/main.js?approval-history-success=${Date.now()}`);
  await settle();
  clickPage("approval-history");
  await settle();

  const text = document.querySelector("main.content")?.textContent || "";
  assert.ok(calls.includes("/api/v1/approvals/history"));
  assert.equal(document.querySelector("main.content h2 small"), null);
  assert.match(text, /审批历史|APPROVAL-HISTORY-1|REQUEST-HISTORY-1|APPROVED/);
  assert.doesNotMatch(text, /undefined|null|NaN|\[object Object\]/);
  assert.ok(!document.querySelector("main.content > .api-state.error"));
});

test("a late pending-approval failure does not contaminate the loaded history table", async () => {
  const { releasePending } = setup({ delayedPendingFailure: true });
  await import(`../src/main.js?approval-history-isolation=${Date.now()}`);
  await settle();
  clickPage("approval-history");
  await settle();
  clickPage("pending-approvals");
  clickPage("approval-history");
  releasePending();
  await settle();

  const text = document.querySelector("main.content")?.textContent || "";
  assert.match(text, /APPROVAL-HISTORY-1/);
  assert.ok(!document.querySelector("main.content > .api-state.error"));
  assert.doesNotMatch(text, /undefined|null|NaN|\[object Object\]|pending service unavailable/);
});

test("a core history failure uses the fixed user-facing message", async () => {
  setup({ historyFails: true });
  await import(`../src/main.js?approval-history-failure=${Date.now()}`);
  await settle();
  clickPage("approval-history");
  await settle();

  const error = document.querySelector("main.content > .api-state.error")?.textContent || "";
  assert.equal(error, "审批历史加载失败，请稍后重试");
  assert.doesNotMatch(document.querySelector("main.content")?.textContent || "", /undefined|null|NaN|\[object Object\]|database unavailable/);
});
