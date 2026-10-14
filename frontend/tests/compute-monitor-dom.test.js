import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { JSDOM } from "jsdom";

process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://127.0.0.1:8000";

const analyst = { user_id: "analyst_demo", username: "analyst_demo", role: "ANALYST", party_id: null, is_active: true };
const task = {
  task_id: "TASK-MONITOR-1", query_type: "SUM", parties: ["ORG_A"], calculation_mode: "DISTRIBUTED_DP",
  epsilon: 1, status: "COMPLETED", duration_ms: 223, created_at: "2026-08-11T10:00:00",
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

function setup({ sparse = false } = {}) {
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
    if (path === "/api/v1/auth/me") return json(analyst);
    if (path === "/api/v1/tasks?limit=50" || path === "/api/v1/tasks?limit=10") return json([task]);
    if (path === "/api/v1/parties") return json([{ organization_id: "ORG_A", status: "online" }]);
    if (path === "/api/v1/system/health") return json({ services: [], checked_at: "2026-08-11T10:00:00" });
    if (path.startsWith("/api/v1/privacy/budgets")) return json({ total_epsilon: 4, used_epsilon: 1, reserved_epsilon: 0, remaining_epsilon: 3 });
    if (path === "/api/v1/tasks/TASK-MONITOR-1/monitor") return json(sparse ? {
      task_id: "TASK-MONITOR-1", status: "COMPLETED", current_stage: null, progress: null,
      party_statuses: { ORG_A: null }, compute_node_statuses: {}, expected_parties: null,
      submitted_share_count: null, started_at: null, updated_at: null, execution_time_ms: null,
    } : {
      task_id: "TASK-MONITOR-1", status: "COMPLETED", current_stage: "COMPLETED", progress: 100,
      party_statuses: { ORG_A: "SHARED" }, compute_node_statuses: { S1: "READY", S2: "READY" },
      expected_parties: ["ORG_A"], submitted_share_count: 1,
      started_at: "2026-08-11T10:00:00", updated_at: "2026-08-11T10:00:00", execution_time_ms: 223,
    });
    return json({ detail: `unexpected ${path}` }, 404);
  };
}

async function openCompute(suffix) {
  await import(`../src/main.js?compute-monitor-${suffix}-${Date.now()}-${Math.random()}`);
  await new Promise((resolve) => setTimeout(resolve, 240));
  document.querySelector('[data-page="compute"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await new Promise((resolve) => setTimeout(resolve, 420));
  return Array.from(document.querySelectorAll(".panel")).find((item) => item.querySelector("h3")?.textContent.includes("任务状态"));
}

test("compute monitor renders the real task status fields without undefined", async () => {
  setup();
  const panel = await openCompute("complete");
  const text = panel?.textContent || "";
  assert.match(text, /任务ID\s*TASK-MONITOR-1/);
  assert.match(text, /当前阶段\s*已完成/);
  assert.match(text, /进度\s*100%/);
  assert.match(text, /园区状态\s*ORG_A: SHARED/);
  assert.match(text, /计算节点状态\s*S1: READY.*S2: READY/);
  assert.match(text, /预计参与方\s*ORG_A/);
  assert.match(text, /已提交份额数\s*1/);
  assert.match(text, /执行时间\s*223 ms/);
  assert.doesNotMatch(text, /undefined|null|NaN|\[object Object\]/);

  const topologyPanel = Array.from(document.querySelectorAll(".panel")).find((item) => item.querySelector("h3")?.textContent.includes("当前任务执行拓扑"));
  const topology = topologyPanel?.querySelector(".task-topology");
  assert.ok(topology);
  const layout = document.querySelector(".task-compute-main");
  assert.ok(layout?.querySelector(":scope > .task-main-column + .task-side-column"));
  assert.ok(layout.querySelector(".task-main-column > .task-topology-panel + .node-budget-grid"));
  assert.ok(layout.querySelector(".node-budget-grid > .node-resources-panel + .privacy-budget-panel"));
  assert.ok(layout.querySelector(".task-side-column > .task-status-panel + .communication-events-panel"));
  assert.equal(layout.querySelectorAll(".task-main-column > .panel").length, 1);
  assert.equal(layout.querySelectorAll(".task-side-column > .panel").length, 2);
  assert.equal(topology.querySelectorAll(".topology-stage").length, 3);
  assert.equal(topology.querySelectorAll(".topology-connector").length, 2);
  assert.match(topology.textContent || "", /参与园区.*ORG_A.*安全计算节点.*S1.*READY.*S2.*READY.*结果已返回/s);
  assert.doesNotMatch(topology.textContent || "", /ORG_B|ORG_C|Agent分析服务|undefined|null|\[object Object\]/);
});

test("compute monitor uses safe dashes for absent optional fields", async () => {
  setup({ sparse: true });
  const panel = await openCompute("sparse");
  const text = panel?.textContent || "";
  assert.match(text, /TASK-MONITOR-1/);
  assert.match(text, /—/);
  assert.doesNotMatch(text, /undefined|null|NaN|\[object Object\]/);
});

test("compute topology uses a compact responsive execution chain", async () => {
  const css = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");
  assert.match(css, /\.task-topology\s*\{[^}]*display:\s*grid[^}]*grid-template-columns:\s*minmax\(150px,\s*1fr\)[^}]*74px[^}]*minmax\(170px,\s*1\.08fr\)/s);
  assert.match(css, /\.topology-connector i::before\s*\{[^}]*flex:\s*1[^}]*height:\s*2px/s);
  assert.match(css, /\.topology-connector i::after\s*\{[^}]*content:\s*"›"/s);
  assert.match(css, /@media \(max-width:\s*1250px\)[\s\S]*?\.task-topology\s*\{\s*grid-template-columns:\s*1fr/s);
  assert.match(css, /\.task-compute-main\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*2\.2fr\)\s+minmax\(320px,\s*\.9fr\)[^}]*align-items:\s*start/s);
  assert.match(css, /\.task-main-column, \.task-side-column\s*\{[^}]*display:\s*flex[^}]*flex-direction:\s*column[^}]*min-width:\s*0[^}]*gap:\s*20px/s);
  assert.match(css, /\.node-budget-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1\.15fr\)\s+minmax\(0,\s*\.85fr\)[^}]*align-items:\s*start/s);
  assert.match(css, /\.task-main-column > \.panel, \.task-side-column > \.panel\s*\{[^}]*margin-bottom:\s*0/s);
  assert.match(css, /@media \(max-width:\s*1390px\)[\s\S]*?\.task-compute-main\s*\{\s*grid-template-columns:\s*1fr/s);
  assert.match(css, /@media \(max-width:\s*1050px\)[\s\S]*?\.node-budget-grid\s*\{\s*grid-template-columns:\s*1fr/s);
  assert.doesNotMatch(css, /\.task-(?:main|side)-column[^}]*height:\s*100%/s);
  assert.doesNotMatch(css, /\.topology-connector[^}]*position:\s*absolute/s);
});
