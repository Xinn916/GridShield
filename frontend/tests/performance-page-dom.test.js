import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { JSDOM } from "jsdom";

process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://127.0.0.1:8000";

const analyst = { user_id: "analyst_demo", username: "analyst_demo", role: "ANALYST", party_id: null, is_active: true };
const services = [
  ["control", true, 3], ["frontend", true, 2], ["party-a", true, 5], ["party-b", false, null],
  ["party-c", true, 6], ["compute-s1", true, 4], ["compute-s2", true, 4],
].map(([service_id, online, latency_ms]) => ({ service_id, name: service_id, online, latency_ms, version: "0.4.0" }));

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

function setup() {
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
  const calls = [];
  globalThis.fetch = async (url) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    calls.push(path);
    if (path === "/api/v1/auth/me") return json(analyst);
    if (path === "/api/v1/system/health") return json({ services, checked_at: "2026-08-13T10:00:00" });
    if (path === "/api/v1/performance-tests?limit=10&offset=0") return json({ items: [], total: 0, limit: 10, offset: 0 });
    if (path === "/api/v1/performance-tests") return json({
      id: "PERF-REAL-1", benchmark_id: "ENERGY_BENCHMARK_V1", parties: ["ORG_A", "ORG_B", "ORG_C"],
      query_type: "SUM", mode: "DISTRIBUTED_DP", epsilon: 1, interval: null, status: "COMPLETED",
      summary: { total_duration_ms: 12.5, communication_bytes: 4096, participant_nodes: 6, total_nodes: 6, average_response_ms: 2.5 },
      phases: [
        { key: "parameter_validation", label: "参数与模式校验", duration_ms: 0.35 },
        { key: "local_statistics", label: "本地数据读取与统计", duration_ms: 7.5 },
        { key: "result_reconstruction", label: "结果汇总", duration_ms: 0.65 },
      ],
      links: [{ test_id: "PERF-REAL-1", source_node: "control", target_node: "party-a", operation: "statistics", request_bytes: 100, response_bytes: 200, total_bytes: 300, duration_ms: 2.5, started_at: "2026-08-13T10:00:00", completed_at: "2026-08-13T10:00:01" }],
      error: null, created_at: "2026-08-13T10:00:00", started_at: "2026-08-13T10:00:00", completed_at: "2026-08-13T10:00:01",
    }, 201);
    return json({ detail: `unexpected ${path}` }, 404);
  };
  return calls;
}

async function openPerformance() {
  const calls = setup();
  await import(`../src/main.js?benchmark=${Date.now()}-${Math.random()}`);
  await new Promise((resolve) => setTimeout(resolve, 160));
  document.querySelector('[data-page="performance"]').dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await new Promise((resolve) => setTimeout(resolve, 260));
  return { calls, main: document.querySelector("main.performance-page") };
}

test("performance page is an independent synthetic benchmark without catalog or grant calls", async () => {
  const { calls, main } = await openPerformance();
  const text = main?.textContent || "";
  assert.equal(main?.querySelector("h2 small"), null);
  assert.equal(main?.querySelector(".performance-benchmark-note"), null);
  assert.equal(document.querySelector("#performance-benchmark")?.value, "ENERGY_BENCHMARK_V1");
  assert.match(text, /标准三方能源数据基准集/);
  assert.match(text, /合成能源负荷数据/);
  assert.equal(calls.includes("/api/v1/system/health"), true);
  assert.equal(calls.includes("/api/v1/catalog/assets"), false);
  assert.equal(calls.includes("/api/v1/grants/mine"), false);
  assert.equal(calls.includes("/api/v1/performance-tests?limit=10&offset=0"), true);
  assert.doesNotMatch(text, /真实数据|生产数据|已授权数据/);
});

test("all Benchmark Parties are independently selectable and default to three parties", async () => {
  const { main } = await openPerformance();
  const parties = [...document.querySelectorAll('input[name="performance-party"]')];
  assert.deepEqual(parties.map((item) => item.value), ["ORG_A", "ORG_B", "ORG_C"]);
  assert.equal(parties.every((item) => !item.disabled && item.checked), true);
  assert.match(main.textContent, /参与方\s*3/);

  parties[1].checked = false;
  parties[1].dispatchEvent(new Event("change", { bubbles: true }));
  assert.match(document.querySelector("main.performance-page").textContent, /参与方\s*2/);
  assert.equal(document.querySelector('input[value="ORG_A"][name="performance-party"]')?.checked, true);
  assert.equal(document.querySelector('input[value="ORG_B"][name="performance-party"]')?.checked, false);
});

test("epsilon follows privacy mode and an empty Party selection is rejected without fake metrics", async () => {
  const { calls } = await openPerformance();
  const epsilon = () => document.querySelector("#performance-epsilon");
  assert.equal(epsilon().disabled, false);

  const plain = document.querySelector('input[name="performance-mode"][value="PLAIN"]');
  plain.checked = true;
  plain.dispatchEvent(new Event("change", { bubbles: true }));
  assert.equal(epsilon().disabled, true);

  const secret = document.querySelector('input[name="performance-mode"][value="SECRET_SHARE"]');
  secret.checked = true;
  secret.dispatchEvent(new Event("change", { bubbles: true }));
  assert.equal(epsilon().disabled, true);

  const dp = document.querySelector('input[name="performance-mode"][value="DISTRIBUTED_DP"]');
  dp.checked = true;
  dp.dispatchEvent(new Event("change", { bubbles: true }));
  assert.equal(epsilon().disabled, false);

  while (document.querySelector('input[name="performance-party"]:checked')) {
    const party = document.querySelector('input[name="performance-party"]:checked');
    party.checked = false;
    party.dispatchEvent(new Event("change", { bubbles: true }));
  }
  document.querySelector('[data-action="start-performance"]').dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await new Promise((resolve) => setTimeout(resolve, 40));
  const text = document.body.textContent || "";
  assert.match(text, /至少选择一个 Benchmark Party/);
  assert.doesNotMatch(text, /428|37\.6|152|12\.4|9\.8|PERF-2026|undefined|null|NaN|\[object Object\]/);
  assert.equal(calls.includes("/api/v1/performance-tests"), false);
});

test("time interval has no selected box unless TIME_SERIES is active", async () => {
  await openPerformance();
  assert.equal(document.querySelectorAll('input[name="performance-interval"]').length, 0);
  assert.match(document.querySelector("main.performance-page")?.textContent || "", /仅 TIME_SERIES 可设置/);

  const timeSeries = document.querySelector('input[name="performance-query-type"][value="TIME_SERIES"]');
  timeSeries.checked = true;
  timeSeries.dispatchEvent(new Event("change", { bubbles: true }));

  const intervals = [...document.querySelectorAll('input[name="performance-interval"]')];
  assert.equal(intervals.length, 3);
  assert.equal(intervals.every((item) => !item.disabled), true);
  assert.equal(intervals.filter((item) => item.checked).length, 1);
  assert.equal(intervals.find((item) => item.checked)?.value, "30m");
});

test("start binds real performance metadata and never renders a business result", async () => {
  const { calls } = await openPerformance();
  document.querySelector('[data-action="start-performance"]').dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await new Promise((resolve) => setTimeout(resolve, 80));
  const text = document.querySelector("main.performance-page")?.textContent || "";
  assert.match(text, /阶段总耗时\s*1(?:\.00)?\s*ms/);
  assert.match(text, /参数与模式校验[\s\S]*0\.35\s*ms/);
  assert.match(text, /结果汇总[\s\S]*0\.65\s*ms/);
  assert.match(text, /通信总量\s*4\.00\s*KB/);
  assert.match(text, /参与节点\s*6 \/ 6/);
  assert.doesNotMatch(text, /本地数据读取与统计/);
  assert.match(text, /control.*party-a/s);
  assert.match(text, /PERF-REAL-1/);
  assert.doesNotMatch(text, /SUM\s*=|result\s*=|value\s*=|series\s*=|secret share content|DP noise/i);
  assert.equal(calls.includes("/api/v1/performance-tests"), true);
});

test("performance layout uses independent columns and responsive breakpoints", async () => {
  const css = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");
  assert.match(css, /\.performance-layout\s*\{[^}]*grid-template-columns:[^}]*align-items:\s*start/s);
  assert.match(css, /\.performance-column\s*\{[^}]*display:\s*flex[^}]*flex-direction:\s*column/s);
  assert.match(css, /@media \(max-width:\s*1390px\)[\s\S]*?\.performance-layout\s*\{\s*grid-template-columns:\s*1fr/s);
  assert.doesNotMatch(css, /\.performance-column[^}]*height:\s*100%/s);
});
