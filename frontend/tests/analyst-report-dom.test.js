import { test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://127.0.0.1:8000";

const analyst = { user_id: "analyst_demo", username: "analyst_demo", role: "ANALYST", party_id: null, is_active: true };

const populatedReport = {
  total_tasks: 2,
  completed_tasks: 1,
  failed_tasks: 1,
  success_rate: 50,
  average_task_duration_ms: 3000,
  epsilon_consumed: 1,
  remaining_privacy_budget: 19,
  query_type_counts: { SUM: 1, COUNT: 0, AVERAGE: 0, TIME_SERIES: 1 },
  party_participation_counts: { ORG_A: 1, ORG_B: 2, ORG_C: 0 },
  time_series_bucket_count: 24,
  recent_tasks: [{
    task_id: "TASK-REPORT-1", query_type: "TIME_SERIES", parties: ["ORG_A", "ORG_B"],
    status: "COMPLETED", epsilon: 1, created_at: "2026-08-01T10:00:00",
    completed_at: "2026-08-01T10:00:02", grant_id: "GRANT-REPORT-1", bucket_count: 24,
  }, {
    task_id: "TASK-REPORT-2", query_type: "SUM", parties: ["ORG_B"], status: "FAILED",
    epsilon: 0.5, created_at: "2026-08-01T10:01:00", completed_at: "2026-08-01T10:01:04",
    grant_id: "GRANT-REPORT-1", bucket_count: null,
  }],
  recent_grant_usage: [{
    task_id: "TASK-REPORT-1", grant_id: "GRANT-REPORT-1", epsilon: 1, status: "CONSUMED",
    remaining_before: 4, remaining_after: 3, created_at: "2026-08-01T10:00:00",
    updated_at: "2026-08-01T10:00:02",
  }],
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

function setup(report) {
  const dom = new JSDOM("<!doctype html><html><body><div id='app'></div></body></html>", { url: "http://localhost:5173/", pretendToBeVisual: true });
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.HTMLElement = dom.window.HTMLElement;
  globalThis.Element = dom.window.Element;
  globalThis.Node = dom.window.Node;
  globalThis.MouseEvent = dom.window.MouseEvent;
  globalThis.Event = dom.window.Event;
  globalThis.fetch = async (url) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    if (path === "/api/v1/auth/me") return json(analyst);
    if (path === "/api/v1/reports/me?limit=20") return json(report);
    if (path === "/api/v1/grants/mine") return json([]);
    if (path.startsWith("/api/v1/tasks")) return json([]);
    if (path === "/api/v1/parties") return json([]);
    if (path === "/api/v1/system/health") return json({ services: [], checked_at: "2026-08-05T00:00:00" });
    if (path.startsWith("/api/v1/privacy/budgets")) return json({ total_epsilon: 20, used_epsilon: 1, reserved_epsilon: 0, remaining_epsilon: 19 });
    return json({ detail: `unexpected ${path}` }, 404);
  };
}

async function openReport(report, key) {
  setup(report);
  await import(`../src/main.js?${key}=${Date.now()}`);
  await new Promise((resolve) => setTimeout(resolve, 120));
  document.querySelector('[data-page="report"]').dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await new Promise((resolve) => setTimeout(resolve, 160));
  return document.querySelector("main.content")?.textContent || "";
}

test("analyst report renders metrics computed from real task records", async () => {
  const text = await openReport(populatedReport, "analyst-report");
  for (const expected of [
    "总任务数", "COMPLETED", "FAILED", "50%", "3.00 s", "1 ε", "19 ε",
    "TIME_SERIES 桶数", "24", "TASK-REPORT-1", "TASK-REPORT-2", "GRANT-REPORT-1",
    "ORG_A", "ORG_B", "CONSUMED", "PDF 下载当前版本未开放",
    "隐私保护方法原理对比", "该表为方法学说明，不代表当前在线实验测量结果",
    "隐私效用及攻击实验指标由离线实验脚本生成，不属于在线业务统计",
  ]) assert.match(text, new RegExp(expected));

  assert.doesNotMatch(text, /NaN|Infinity|undefined|\[object Object\]|RPT-20250518|重构攻击成功率|成员推断准确率|RMSE|MAPE|通信量|查询计划正确率/);
  const pdfButton = Array.from(document.querySelectorAll("button"))
    .find((button) => button.textContent.includes("PDF 下载当前版本未开放"));
  assert.ok(pdfButton?.disabled);
});

test("analyst report renders finite zero metrics and truthful empty states", async () => {
  const empty = {
    total_tasks: 0, completed_tasks: 0, failed_tasks: 0, success_rate: 0,
    average_task_duration_ms: 0, epsilon_consumed: 0, remaining_privacy_budget: 20,
    query_type_counts: { SUM: 0, COUNT: 0, AVERAGE: 0, TIME_SERIES: 0 },
    party_participation_counts: { ORG_A: 0, ORG_B: 0, ORG_C: 0 },
    time_series_bucket_count: 0, recent_tasks: [], recent_grant_usage: [],
  };
  const text = await openReport(empty, "analyst-report-empty");
  assert.match(text, /暂无真实任务/);
  assert.match(text, /暂无授权使用记录/);
  assert.doesNotMatch(text, /NaN|Infinity|undefined|null|\[object Object\]/);
});
