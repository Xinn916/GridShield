import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { JSDOM } from "jsdom";

process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://127.0.0.1:8000";

const owner = { user_id: "owner_a", username: "owner_a", role: "DATA_OWNER", party_id: "ORG_A", is_active: true };
const roleUsers = [
  owner,
  { user_id: "auditor_demo", username: "auditor_demo", role: "AUDITOR", party_id: null, is_active: true },
  { user_id: "analyst_demo", username: "analyst_demo", role: "ANALYST", party_id: null, is_active: true },
  { user_id: "admin_demo", username: "admin_demo", role: "ADMIN", party_id: null, is_active: true },
];
const services = [
  ["control-plane", "总控服务", true, 8.3, "0.4.0", "http://127.0.0.1:8000"],
  ["frontend", "前端网关 Nginx", true, 5.1, "1.27", "http://frontend"],
  ["party-a", "园区 A", true, 2.9, "0.4.0", "http://party-a:8101"],
  ["party-b", "园区 B", false, 5.8, "0.4.0", "http://party-b:8102"],
  ["party-c", "园区 C", true, 3.1, "0.4.0", "http://party-c:8103"],
  ["compute-s1", "计算节点 S1", true, 4.2, "0.4.0", "http://compute-s1:8201"],
  ["compute-s2", "计算节点 S2", true, 2.3, "0.4.0", "http://compute-s2:8202"],
].map(([service_id, name, online, latency_ms, version, endpoint]) => ({ service_id, name, online, latency_ms, version, endpoint }));

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

function setup(user = owner) {
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
  const calls = [];
  globalThis.fetch = async (url) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    calls.push(path);
    if (path === "/api/v1/public/config") return json({ app_env: "development" });
    if (path === "/api/v1/auth/me") return json(user);
    if (path === "/api/v1/system/health") return json({ services, checked_at: "2026-08-10T10:00:00" });
    if (path === "/api/v1/parties") return json([{ party_id: "ORG_A", status: "online" }]);
    if (path === "/api/v1/tasks?limit=50") return json([
      { task_id: "TASK-1", query_type: "SUM", parties: ["ORG_A"], calculation_mode: "DISTRIBUTED_DP", status: "COMPLETED", duration_ms: 100, created_at: "2026-08-10T08:00:00" },
      { task_id: "TASK-2", query_type: "TIME_SERIES", parties: ["ORG_A", "ORG_B"], calculation_mode: "DISTRIBUTED_DP", status: "FAILED", duration_ms: 200, created_at: "2026-08-09T08:00:00" },
    ]);
    if (path === "/api/v1/privacy/budgets?subject_id=demo-analyst&data_scope=GLOBAL") return json({ total_epsilon: 20, used_epsilon: 2, reserved_epsilon: 0, remaining_epsilon: 18 });
    if (path === "/api/v1/approvals/pending") return json([{ approval_id: "P-1" }, { approval_id: "P-2" }]);
    if (path === "/api/v1/approvals/history") return json([{ approval_id: "H-1", decided_at: "2026-08-09T09:00:00" }]);
    if (path === "/api/v1/grants/owner") return json([{ grant_id: "G-1", status: "ACTIVE" }, { grant_id: "G-2", status: "EXPIRED" }]);
    if (path === "/api/v1/data-imports/active") return json({ dataset_version: "IMPORT-000003", status: "ACTIVE" });
    if (path === "/api/v1/data-imports/mine") return json([{ import_id: "IMPORT-000003", status: "VALID", created_at: "2026-08-08T10:00:00" }]);
    return json({ detail: `unexpected ${path}` }, 404);
  };
  return calls;
}

async function settle(ms = 260) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

test("owner overview uses independent compact chart and health columns with real summaries", async () => {
  const calls = setup();
  await import(`../src/main.js?overview-layout=${Date.now()}`);
  await settle();

  const main = document.querySelector("main.overview");
  assert.ok(main);
  assert.equal(main.querySelectorAll(".overview-chart-card").length, 2);
  assert.equal(main.querySelectorAll(".overview-charts > .overview-chart-card").length, 2);
  assert.ok(main.querySelector(".dashboard-left + .dashboard-right"));
  assert.ok(main.querySelector(".dashboard-left > .recent-tasks-panel"));
  assert.ok(main.querySelector(".dashboard-right > .overview-health-panel + .overview-risk-panel"));
  assert.ok(!main.querySelector(".grid-2-1.bottom"));
  assert.equal(main.querySelectorAll(".health-item").length, 7);
  assert.equal(main.querySelectorAll(".business-summary-card").length, 4);

  const text = main.textContent || "";
  for (const expected of [
    "待处理审批", "2", "已完成 1", "本园区有效授权", "授权记录 2 条",
    "IMPORT-000003", "最近导入 VALID", "最近任务", "最多 50 条",
    "总控服务", "前端网关 Nginx", "园区 A", "计算节点 S2", "ONLINE", "OFFLINE", "版本 0.4.0",
  ]) assert.match(text, new RegExp(expected));
  assert.doesNotMatch(text, /http:\/\/|undefined|null|NaN|\[object Object\]/);
  assert.equal(document.querySelector(".topbar .env, .topbar .env-wrap"), null);
  assert.ok(!calls.includes("/api/v1/public/config"), "ordinary pages must not request APP_ENV for presentation");

  for (const path of [
    "/api/v1/approvals/pending", "/api/v1/approvals/history", "/api/v1/grants/owner",
    "/api/v1/data-imports/active", "/api/v1/data-imports/mine", "/api/v1/tasks?limit=50",
  ]) assert.ok(calls.includes(path), `missing real data request: ${path}`);
});

test("overview CSS fixes chart height and disables grid stretching at target widths", async () => {
  const css = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");
  assert.match(css, /\.overview-dashboard\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*2\.2fr\)\s+minmax\(320px,\s*1fr\)[^}]*align-items:\s*start/s);
  assert.match(css, /\.dashboard-left, \.dashboard-right\s*\{[^}]*display:\s*flex[^}]*flex-direction:\s*column[^}]*min-width:\s*0[^}]*gap:\s*16px/s);
  assert.match(css, /\.dashboard-left > \.panel, \.dashboard-right > \.panel\s*\{\s*margin-bottom:\s*0/);
  assert.match(css, /\.overview-chart-card\s*\{[^}]*height:\s*340px/s);
  assert.match(css, /\.overview-chart-card \.chart svg\s*\{[^}]*height:\s*240px[^}]*max-height:\s*240px/s);
  assert.match(css, /@media \(max-width:\s*1390px\)[\s\S]*?\.overview-dashboard\s*\{\s*grid-template-columns:\s*1fr/s);
  assert.match(css, /@media \(max-width:\s*1100px\)[\s\S]*?\.overview-charts\s*\{\s*grid-template-columns:\s*1fr/s);
  assert.doesNotMatch(css, /\.overview-chart-card\s*\{[^}]*height:\s*100%/s);
  assert.match(css, /\.top-actions\s*\{[^}]*display:\s*flex[^}]*gap:\s*14px[^}]*min-width:\s*0[^}]*margin-left:\s*24px/s);
  assert.match(css, /@media\s*\(max-width:\s*1400px\)[\s\S]*?\.top-actions\s*\{[^}]*gap:\s*10px[^}]*margin-left:\s*16px/s);
  assert.doesNotMatch(css, /\.env(?:-wrap|-development|-testing|-production|-unavailable|\s*\{)/);
});

test("shared overview has no empty grid slots for owner, auditor, analyst or admin", async () => {
  for (const user of roleUsers) {
    setup(user);
    await import(`../src/main.js?overview-role-${user.role}=${Date.now()}-${Math.random()}`);
    await settle(180);
    if (!document.querySelector("main.overview")) {
      document.querySelector('[data-page="overview"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await settle();
    }
    const main = document.querySelector("main.overview");
    assert.ok(main, `${user.role} overview must render`);
    assert.ok(main.querySelector(".dashboard-left > .recent-tasks-panel"));
    assert.ok(main.querySelector(".dashboard-right > .overview-health-panel + .overview-risk-panel"));
    assert.equal(main.querySelectorAll(".business-overview-panel").length, user.role === "DATA_OWNER" ? 1 : 0);
    assert.doesNotMatch(main.textContent || "", /undefined|null|NaN|\[object Object\]/);
    const topbar = document.querySelector(".topbar");
    assert.ok(topbar?.querySelector('[data-action="open-search"]'));
    assert.ok(topbar?.querySelector('[data-action="toggle-notify"]'));
    assert.ok(topbar?.querySelector('[data-action="toggle-user"]'));
    assert.ok(topbar?.querySelector(".top-actions > .search + .bell-wrap"));
    assert.ok(topbar?.querySelector(".top-actions > .bell-wrap + .user-wrap"));
    assert.equal(topbar?.querySelector(".env, .env-wrap"), null);
    assert.doesNotMatch(topbar?.textContent || "", /开发环境|测试环境|生产环境|环境未配置|环境状态未知/);
    topbar?.querySelector('[data-action="toggle-notify"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    assert.ok(document.querySelector(".drawer-open .drawer"), `${user.role} notification drawer must open`);
    document.querySelector('[data-action="toggle-notify"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    document.querySelector('[data-action="toggle-user"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    assert.ok(document.querySelector(".user-wrap .popover"), `${user.role} user menu must open`);
  }
});
