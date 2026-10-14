import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { JSDOM } from "jsdom";

process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://127.0.0.1:8000";

const users = {
  ANALYST: { user_id: "analyst_demo", username: "analyst_demo", role: "ANALYST", party_id: null, is_active: true },
  DATA_OWNER: { user_id: "owner_a", username: "owner_a", role: "DATA_OWNER", party_id: "ORG_A", is_active: true },
  ADMIN: { user_id: "admin_demo", username: "admin_demo", role: "ADMIN", party_id: null, is_active: true },
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

test("search result hidden rows are not forced visible by flex styling", async () => {
  const css = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");
  assert.match(css, /\.search-result\[hidden\]\s*\{[^}]*display:\s*none\s*!important/);
});

function setup(user = users.DATA_OWNER) {
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
  globalThis.localStorage = dom.window.localStorage;
  globalThis.fetch = async (url) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    if (path === "/api/v1/auth/me") return json(user);
    if (path === "/api/v1/public/config") return json({ app_env: "development" });
    if (path === "/api/v1/data-imports/mine") return json([]);
    if (path === "/api/v1/data-imports/active") return json({ detail: "none" }, 404);
    if (path === "/api/v1/data-imports/config") return json({ max_upload_bytes: 1048576 });
    if (path === "/api/v1/catalog/assets/mine") return json([]);
    if (path === "/api/v1/system/policy-summary") return json({});
    if (path === "/api/v1/system/health") return json({ services: [], checked_at: "2026-08-15T00:00:00" });
    if (path === "/api/v1/admin/system-overview") return json({
      database: { type: "SQLite", connected: true, demo_database: true, note: "test" },
      asset_storage: { type: "Parquet", party_count: 3, mount_mode: "READ_ONLY" },
      frontend_gateway: { service_id: "frontend", name: "frontend", online: true, latency_ms: 1 },
      party_nodes: [], compute_nodes: [], agent_model_configured: false,
      security_baseline: {}, system_events: [], maintenance_records: [], planned_extensions: [],
      checked_at: "2026-08-15T00:00:00",
    });
    if (path.startsWith("/api/v1/")) return json([]);
    return json({}, 404);
  };
  return dom;
}

function click(selector) {
  const element = document.querySelector(selector);
  assert.ok(element, `element not found: ${selector}`);
  element.dispatchEvent(new MouseEvent("click", { bubbles: true }));
}

async function settle(ms = 140) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

test("global search closes cleanly and routes only real owner features", async () => {
  const dom = setup();
  await import(`../src/main.js?search-interactions=${Date.now()}`);
  await settle();

  click('[data-action="open-search"]');
  assert.ok(document.querySelector(".search-modal"));
  click('.search-modal [aria-label="关闭全局搜索"]');
  assert.ok(!document.querySelector(".overlay"), "close button must remove the overlay");

  click('[data-action="open-search"]');
  document.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  assert.ok(!document.querySelector(".overlay"), "Escape must remove the overlay");

  click('[data-action="open-search"]');
  click('.overlay');
  assert.ok(!document.querySelector(".overlay"), "backdrop click must remove the overlay");

  click('[data-action="open-search"]');
  assert.match(document.querySelector(".search-modal")?.textContent || "", /暂无最近搜索/);
  assert.doesNotMatch(document.querySelector(".search-modal")?.textContent || "", /园区A 昨日负荷|VPP_FLEXIBILITY_ANALYSIS|TASK-20250518/);
  click('[data-feature="data"].search-function');
  assert.ok(document.querySelector('[data-page="data"].active'));
  assert.ok(!document.querySelector(".overlay"));

  click('[data-action="open-search"]');
  click('[data-feature="policy"].search-function');
  assert.ok(document.querySelector('[data-page="policy"].active'));

  click('[data-action="open-search"]');
  const input = document.querySelector("#global-search-input");
  input.value = "数据接入";
  input.dispatchEvent(new Event("input", { bubbles: true }));
  const result = document.querySelector('.search-result[data-feature="data"]');
  assert.ok(result && !result.hidden, "known keywords must expose a navigable result");
  result.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  assert.ok(document.querySelector('[data-page="data"].active'));
  assert.equal(document.querySelectorAll(".toast").length, 0, "successful navigation needs no redundant toast");

  click('[data-action="open-search"]');
  assert.ok(document.querySelector('[data-action="search-chip"][data-q="数据接入"]'));
});

test("analyst keyword opens the real performance page", async () => {
  setup(users.ANALYST);
  await import(`../src/main.js?search-analyst=${Date.now()}`);
  await settle();
  click('[data-action="open-search"]');
  const input = document.querySelector("#global-search-input");
  input.value = "分布式隐私计算";
  input.dispatchEvent(new Event("input", { bubbles: true }));
  const visible = [...document.querySelectorAll(".search-result:not([hidden])")];
  assert.deepEqual(visible.map((item) => item.dataset.feature), ["performance"]);
  assert.match(visible[0].textContent, /性能测试/);
  visible[0].dispatchEvent(new MouseEvent("click", { bubbles: true }));
  assert.ok(document.querySelector('[data-page="performance"].active'));
  assert.doesNotMatch(document.body.textContent || "", /已打开：分布式隐私计算/);
});

test("admin cannot see or navigate analyst-only distributed privacy feature", async () => {
  const dom = setup(users.ADMIN);
  await import(`../src/main.js?search-admin=${Date.now()}`);
  await settle();
  click('[data-action="open-search"]');
  const modal = document.querySelector(".search-modal");
  assert.deepEqual(
    [...modal.querySelectorAll(".search-function")].map((item) => item.dataset.feature),
    ["admin-requests", "admin-grants", "security-audit", "settings"],
  );
  assert.equal(modal.querySelector('[data-feature="performance"]'), null);
  const input = modal.querySelector("#global-search-input");
  input.value = "分布式隐私计算";
  input.dispatchEvent(new Event("input", { bubbles: true }));
  assert.equal(modal.querySelectorAll(".search-result:not([hidden])").length, 0);
  assert.ok(modal.querySelector(".search-result-list").hidden);
  assert.match(modal.textContent, /未找到相关功能/);
  input.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  assert.ok(document.querySelector('[data-page="settings"].active'));
  assert.doesNotMatch(document.body.textContent || "", /已打开/);
});

test("search switches between idle and true matching states", async () => {
  setup(users.ADMIN);
  await import(`../src/main.js?search-states=${Date.now()}`);
  await settle();
  click('[data-action="open-search"]');
  const modal = document.querySelector(".search-modal");
  const input = modal.querySelector("#global-search-input");
  const idle = modal.querySelector(".search-idle-content");
  const results = modal.querySelector("#global-search-results");

  assert.ok(!idle.hidden, "empty query should show recent/common content");
  assert.ok(results.hidden, "empty query should hide matching results");

  input.value = "全部";
  input.dispatchEvent(new Event("input", { bubbles: true }));
  assert.ok(idle.hidden, "non-empty query should hide recent/common content");
  assert.ok(!results.hidden, "non-empty query should show matching results");
  assert.equal(results.querySelectorAll(".search-result:not([hidden])").length, 2, "全部 should match only real admin titles");
  assert.match(modal.querySelector("#global-search-count").textContent, /^2 项$/);

  input.value = "";
  input.dispatchEvent(new Event("input", { bubbles: true }));
  assert.ok(!idle.hidden, "clearing query should restore idle content");
  assert.ok(results.hidden, "clearing query should hide matching results");
});

test("search results support keyboard selection and Enter navigation", async () => {
  const dom = setup(users.ADMIN);
  await import(`../src/main.js?search-keyboard=${Date.now()}`);
  await settle();
  click('[data-action="open-search"]');
  const input = document.querySelector("#global-search-input");
  input.value = "全部";
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
  assert.equal(document.querySelector('.search-result:not([hidden]).keyboard-selected')?.dataset.feature, "admin-requests");
  input.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  assert.ok(document.querySelector('[data-page="admin-requests"].active'));
  assert.ok(!document.querySelector(".overlay"));
});
