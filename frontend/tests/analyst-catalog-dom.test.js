import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { JSDOM } from "jsdom";

process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://127.0.0.1:8000";

const analyst = { user_id: "analyst_demo", username: "analyst_demo", role: "ANALYST", party_id: null, is_active: true };
const descriptions = {
  ORG_A: "园区家庭用电半小时粒度数据，仅支持受控隐私统计查询。",
  ORG_B: "园区家庭用电半小时粒度数据，仅支持受控隐私统计查询。",
  ORG_C: "园区家庭用电半小时粒度数据，仅支持受控隐私统计查询。",
};
const privacy = "家庭级贡献裁剪、秘密共享与分布式差分隐私；不提供原始数据下载。";
const assets = ["ORG_A", "ORG_B", "ORG_C"].map((party) => ({
  asset_id: `ENERGY_${party}`,
  name: `${party} 园区智能电表聚合数据`,
  description: descriptions[party],
  owner_party: party,
  time_start: "2012-11-11T00:00:00",
  time_end: "2012-12-11T00:00:00",
  source_granularity: "30 min",
  supported_query_types: ["SUM", "COUNT", "AVERAGE", "TIME_SERIES"],
  supported_group_by: ["30m", "1h", "1d"],
  privacy_protection: privacy,
  raw_download_allowed: false,
  status: "ACTIVE",
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
}));

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
  const calls = [];
  globalThis.fetch = async (url) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    calls.push(path);
    if (path === "/api/v1/auth/me") return json(analyst);
    if (path === "/api/v1/catalog/assets") return json(assets);
    if (path === "/api/v1/system/health") return json({ services: [], checked_at: "2026-08-11T10:00:00" });
    if (path === "/api/v1/parties") return json([]);
    if (path === "/api/v1/tasks?limit=50") return json([]);
    if (path.startsWith("/api/v1/privacy/budgets")) return json({ total_epsilon: 0, used_epsilon: 0, reserved_epsilon: 0, remaining_epsilon: 0 });
    return json({ detail: `unexpected ${path}` }, 404);
  };
  return calls;
}

async function settle(ms = 240) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

test("analyst catalog renders compact real metadata and preserves the request flow", async () => {
  const calls = setup();
  await import(`../src/main.js?analyst-catalog=${Date.now()}`);
  await settle();
  document.querySelector('[data-page="catalog"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await settle();

  const page = document.querySelector("main.content");
  const cards = Array.from(page?.querySelectorAll(".catalog-asset-card") || []);
  assert.equal(cards.length, 3);
  assert.ok(calls.includes("/api/v1/catalog/assets"));
  assert.equal(page?.querySelector(".title-row h2")?.textContent, "数据目录");
  assert.equal(page?.querySelectorAll(".catalog-principle").length, 0);

  for (const [index, card] of cards.entries()) {
    const party = `ORG_${String.fromCharCode(65 + index)}`;
    const text = card.textContent || "";
    assert.match(text, new RegExp(`${party} 园区智能电表聚合数据`));
    assert.match(text, new RegExp(`ENERGY_${party}`));
    assert.match(text, /2012\/11\/11 — 2012\/12\/11/);
    assert.match(text, /30 min/);
    assert.match(text, /ACTIVE/);
    assert.equal(card.querySelectorAll(".asset-query-tag").length, 4);
    assert.deepEqual(Array.from(card.querySelectorAll(".asset-query-tag"), (item) => item.textContent), ["SUM", "COUNT", "AVERAGE", "TIME_SERIES"]);
    assert.equal(card.querySelector("p, .notice"), null);
    assert.doesNotMatch(text, /00:00:00|求和 SUM|计数 COUNT|均值 AVERAGE|时间序列 TIME_SERIES/);
    assert.doesNotMatch(text, new RegExp(descriptions[party]));
    assert.doesNotMatch(text, new RegExp(privacy));
    assert.doesNotMatch(text, /undefined|null|\[object Object\]/);
  }

  cards[0].querySelector('[data-action="view-catalog-asset"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  const detail = document.querySelector(".modal");
  assert.ok(detail);
  assert.match(detail.textContent || "", /ENERGY_ORG_A|ORG_A|2012\/11\/11 — 2012\/12\/11|SUM · COUNT · AVERAGE · TIME_SERIES/);
  assert.match(detail.textContent || "", /原始数据由数据提供方本地保存，平台仅支持授权后的受控统计查询/);
  document.querySelector('.modal [data-action="close-overlay"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true }));

  document.querySelectorAll(".catalog-asset-card")[1]?.querySelector('[data-action="apply-asset"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  assert.match(document.querySelector("main.content h2")?.textContent || "", /新建申请/);
  assert.equal(document.querySelector("main.content h2 small"), null);
  assert.equal(document.querySelector("main.content .notice"), null);
  assert.equal(document.querySelector('#ar-parties input[value="ORG_B"]')?.checked, true);
  assert.equal(document.querySelectorAll(".access-form .access-option").length, 10);
  assert.equal(document.querySelector('#ar-parties input[value="ORG_B"] + span')?.textContent, "ORG_B");
  assert.equal(document.querySelector('#ar-types input[value="SUM"] + span')?.textContent, "SUM");
});

test("analyst catalog CSS uses compact cards and responsive columns without overflow", async () => {
  const css = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");
  assert.match(css, /\.catalog-asset-card\s*\{[^}]*display:\s*flex[^}]*flex-direction:\s*column[^}]*min-width:\s*0[^}]*padding:\s*17px 18px 16px/s);
  assert.match(css, /\.asset-query-tags\s*\{[^}]*display:\s*flex[^}]*flex-wrap:\s*wrap/s);
  assert.match(css, /\.catalog-card-actions\s*\{[^}]*margin-top:\s*auto/s);
  assert.match(css, /@media \(max-width:\s*1390px\)[\s\S]*?\.catalog-asset-grid\s*\{\s*grid-template-columns:\s*repeat\(2,/s);
  assert.match(css, /@media \(max-width:\s*760px\)[\s\S]*?\.asset-grid\s*\{\s*grid-template-columns:\s*1fr/s);
  assert.match(css, /\.form2 \.access-option input\[type="checkbox"\]\s*\{[^}]*width:\s*1px[^}]*min-width:\s*0[^}]*opacity:\s*0/s);
  assert.match(css, /\.access-option > span\s*\{[^}]*min-height:\s*32px[^}]*min-width:\s*58px[^}]*border-radius:\s*999px/s);
  assert.match(css, /\.access-option input:checked \+ span\s*\{[^}]*background:\s*#eaf3ff/s);
  assert.match(css, /\.access-option input:disabled \+ span\s*\{[^}]*cursor:\s*not-allowed/s);
});
