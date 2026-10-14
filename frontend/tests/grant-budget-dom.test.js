import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "jsdom";

process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://127.0.0.1:8000";

const user = { user_id: "analyst_demo", username: "analyst_demo", role: "ANALYST", party_id: null, is_active: true };
const baseGrant = (id, remaining) => ({
  grant_id: id,
  request_id: `REQUEST-${id}`,
  grantee_user_id: "analyst_demo",
  parties: ["ORG_A", "ORG_B", "ORG_C"],
  allowed_query_types: ["SUM"],
  allowed_start_time: "2012-11-11T00:00:00",
  allowed_end_time: "2012-11-12T00:00:00",
  allowed_group_by: [],
  max_epsilon_per_query: 5,
  total_epsilon_limit: 20,
  epsilon_consumed: 20 - remaining,
  epsilon_reserved: 0,
  epsilon_remaining: remaining,
  valid_from: "2012-01-01T00:00:00",
  expires_at: "2099-01-01T00:00:00",
  status: "ACTIVE",
  created_at: "2012-01-01T00:00:00",
  revoked_at: null,
});

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

function setup() {
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
  return dom;
}

async function settle(ms = 100) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

test("Grant selector and budget panel stay on one authoritative Grant source", async () => {
  setup();
  let loggedIn = false;
  const grants = { "GRANT-A": baseGrant("GRANT-A", 16), "GRANT-B": baseGrant("GRANT-B", 19) };
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    calls.push(path);
    if (path === "/api/v1/auth/me") return json(loggedIn ? user : { detail: "not logged in" }, loggedIn ? 200 : 401);
    if (path === "/api/v1/auth/login") { loggedIn = true; return json(user); }
    if (path === "/api/v1/grants/mine") return json(Object.values(grants));
    if (path.startsWith("/api/v1/grants/")) return json(grants[path.split("/").pop()] || { detail: "not found" }, grants[path.split("/").pop()] ? 200 : 404);
    if (options.method === "POST" && path === "/api/v1/tasks") {
      return json({ task_id: "TASK-BUDGET-1", status: "CREATED", query_type: "SUM", parties: ["ORG_A"], calculation_mode: "DISTRIBUTED_DP", epsilon: 1 }, 201);
    }
    if (path === "/api/v1/tasks/TASK-BUDGET-1") {
      return json({ task_id: "TASK-BUDGET-1", status: "COMPLETED", query_type: "SUM", parties: ["ORG_A"], calculation_mode: "DISTRIBUTED_DP", epsilon: 1, duration_ms: 2 });
    }
    if (path === "/api/v1/tasks/TASK-BUDGET-1/result") {
      return json({ task_id: "TASK-BUDGET-1", status: "COMPLETED", query_type: "SUM", calculation_mode: "DISTRIBUTED_DP", result: { value: 1 } });
    }
    return json({ detail: "not found" }, 404);
  };

  await import(`../src/main.js?grantbudget=${Date.now()}`);
  document.querySelector("#login-username").value = "analyst_demo";
  document.querySelector("#login-password").value = "password";
  document.querySelector("#login-form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await settle(120);
  const queryCallStart = calls.length;
  document.querySelector('[data-page="query"]').dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await settle(150);

  assert.match(document.querySelector("#q-grant").selectedOptions[0].textContent, /剩余 ε 16/);
  assert.match(document.querySelector("#q-budget").textContent, /剩余预算16/);

  const select = document.querySelector("#q-grant");
  select.value = "GRANT-B";
  select.dispatchEvent(new Event("change", { bubbles: true }));
  await settle(80);
  assert.ok(calls.filter((path) => path === "/api/v1/grants/GRANT-B").length >= 1);
  assert.match(document.querySelector("#q-budget").textContent, /剩余预算19/);

  // A completed query refreshes the selected Grant instead of decrementing
  // the previous browser value locally.
  grants["GRANT-B"] = baseGrant("GRANT-B", 18);
  document.querySelector('[data-action="submit-query"]').dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await settle(750);
  assert.match(document.querySelector("#q-budget").textContent, /剩余预算18/);
  assert.ok(calls.includes("/api/v1/grants/GRANT-B"));
  assert.equal(calls.slice(queryCallStart).some((path) => path.startsWith("/api/v1/privacy/budgets")), false);
});
