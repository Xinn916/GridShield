import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { JSDOM } from "jsdom";

process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://127.0.0.1:8000";

const auditor = {
  user_id: "auditor_demo",
  username: "auditor_demo",
  role: "AUDITOR",
  party_id: null,
  is_active: true,
};

const securityRecord = {
  audit_id: 6,
  event_type: "TASK_CREATED_WITH_GRANT",
  actor_user_id: "analyst_demo",
  actor_role: "ANALYST",
  party_id: null,
  request_id: "REQUEST-000006",
  grant_id: "GRANT-000006",
  task_id: "TASK-000006",
  decision: "CREATED",
  reason: null,
  timestamp: "2026-08-02T10:30:00Z",
};

const taskAudit = {
  task_id: "TASK-000006",
  query_type: "SUM",
  group_by: null,
  bucket_count: null,
  parties: ["ORG_A"],
  epsilon: 1,
  sensitivity: 240,
  mechanism: "distributed_laplace",
  privacy_unit: "household",
  calculation_mode: "DISTRIBUTED_DP",
  budget_before: 20,
  budget_after: 19,
  execution_time_ms: 42,
  status: "COMPLETED",
  created_at: "2026-08-02T10:30:00Z",
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function setup({ records = [securityRecord], tasks = [taskAudit], securityStatus = 200 } = {}) {
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
  globalThis.fetch = async (url) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    if (path === "/api/v1/auth/me") return json(auditor);
    if (path === "/api/v1/admin/security-audit") {
      return securityStatus === 200
        ? json(records)
        : json({ detail: "audit backend unavailable" }, securityStatus);
    }
    if (path === "/api/v1/audit/events?limit=100") return json(tasks);
    if (path.startsWith("/api/v1/tasks")) return json([]);
    if (path === "/api/v1/parties") return json([]);
    if (path === "/api/v1/system/health") return json({ services: [], checked_at: "2026-08-02T10:30:00Z" });
    if (path.startsWith("/api/v1/privacy/budgets")) return json({ total_epsilon: 20, used_epsilon: 1, reserved_epsilon: 0, remaining_epsilon: 19 });
    return json({ detail: `unexpected ${path}` }, 404);
  };
}

async function openAuditPage(cacheKey) {
  await import(`../src/main.js?${cacheKey}=${Date.now()}`);
  await new Promise((resolve) => setTimeout(resolve, 120));
  const menu = document.querySelector('[data-page="audit"]');
  assert.ok(menu, "auditor audit menu should exist");
  menu.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await new Promise((resolve) => setTimeout(resolve, 160));
  return document.querySelector("main.content")?.textContent || "";
}

test("auditor audit page binds real snake_case fields and task budget data", async () => {
  setup();
  const text = await openAuditPage("audit-bindings");
  assert.equal(document.querySelector("main.audit-page h2 small"), null);

  for (const expected of [
    "TASK_CREATED_WITH_GRANT",
    "analyst_demo",
    "TASK-000006",
    "GRANT-000006",
    "REQUEST-000006",
    "SUM",
    "ORG_A",
    "20 ε → 19 ε",
    "未记录",
  ]) assert.match(text, new RegExp(expected));
  assert.doesNotMatch(text, /undefined|null|\[object Object\]/);
  const pdfButton = Array.from(document.querySelectorAll("button"))
    .find((button) => button.textContent.includes("PDF 报告功能开发中"));
  assert.ok(pdfButton?.disabled);
  assert.match(text, /当前后端未提供风险评估字段/);
});

test("auditor audit page shows the truthful empty state", async () => {
  setup({ records: [], tasks: [] });
  const text = await openAuditPage("audit-empty");
  assert.match(text, /暂无查询和预算审计记录/);
  assert.doesNotMatch(text, /undefined|null|\[object Object\]/);
});

test("auditor audit page shows a safe API error state", async () => {
  setup({ securityStatus: 503 });
  const text = await openAuditPage("audit-error");
  assert.match(text, /审计记录加载失败：audit backend unavailable/);
  assert.doesNotMatch(text, /undefined|null|\[object Object\]/);
});

test("auditor audit layout contains long records and a bounded vertical event timeline", async () => {
  const records = Array.from({ length: 10 }, (_, index) => ({
    ...securityRecord,
    audit_id: 100 - index,
    event_type: `VERY_LONG_SECURITY_EVENT_TYPE_${index}_WITH_SUFFIX`,
    actor_user_id: `auditor-subject-${index}-${"x".repeat(40)}`,
    task_id: `TASK-${index}-${"9".repeat(40)}`,
    timestamp: `2026-08-${String(10 - index).padStart(2, "0")}T10:30:00Z`,
  }));
  setup({ records, tasks: [taskAudit] });
  const text = await openAuditPage("audit-responsive-layout");
  const main = document.querySelector("main.audit-page");

  assert.ok(main?.querySelector(".audit-primary-grid"));
  assert.ok(main?.querySelector(".audit-detail-grid"));
  assert.ok(main?.querySelector(".audit-table-scroll > .audit-records-table"));
  assert.equal(main?.querySelectorAll(".audit-kpis .stat").length, 3);
  assert.equal(main?.querySelectorAll(".audit-timeline-item").length, 6, "timeline must be capped at six real records");
  assert.ok(!main?.querySelector(".chain, .chain-arrow"), "the event chain must not remain in one horizontal row");
  assert.match(text, /#100 · VERY_LONG_SECURITY_EVENT_TYPE_0_WITH_SUFFIX/);
  assert.doesNotMatch(text, /undefined|null|NaN|\[object Object\]/);
});

test("auditor layout CSS constrains the page and only permits local table overflow", async () => {
  const css = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");
  assert.match(css, /\.content\s*\{[^}]*min-width:\s*0[^}]*max-width:\s*100%/s);
  assert.match(css, /\.audit-page\s*\{[^}]*width:\s*100%[^}]*max-width:\s*100%[^}]*min-width:\s*0/s);
  assert.match(css, /\.audit-primary-grid\s*\{[^}]*minmax\(0,\s*1\.7fr\)\s+minmax\(320px,\s*1fr\)[^}]*align-items:\s*start/s);
  assert.match(css, /\.audit-primary-grid > \*, \.audit-detail-grid > \*\s*\{\s*min-width:\s*0/);
  assert.match(css, /\.audit-table-scroll\s*\{[^}]*max-width:\s*100%[^}]*overflow-x:\s*auto/s);
  assert.match(css, /\.audit-kpis\s*\{[^}]*repeat\(auto-fit,\s*minmax\(135px,\s*1fr\)\)/s);
  assert.match(css, /@media \(max-width:\s*1390px\)[\s\S]*?\.audit-primary-grid, \.audit-detail-grid\s*\{\s*grid-template-columns:\s*minmax\(0,\s*1fr\)/s);
  assert.doesNotMatch(css, /\.audit-page\s*\{[^}]*overflow-x:\s*hidden/s);
  assert.doesNotMatch(css, /\.audit-primary-grid\s*\{[^}]*width:\s*\d{3,}px/s);
  assert.doesNotMatch(css, /\.topbar\s*\{[^}]*(?:position:\s*fixed|position:\s*sticky)/s);
});
