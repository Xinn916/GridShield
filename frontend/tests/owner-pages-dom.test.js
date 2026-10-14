import { test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://127.0.0.1:8000";


const owner = {
  user_id: "owner_a",
  username: "owner_a",
  role: "DATA_OWNER",
  party_id: "ORG_A",
  is_active: true,
};

const asset = {
  asset_id: "ENERGY_ORG_A",
  name: "ORG_A 园区智能电表聚合数据",
  description: "仅支持受控隐私统计查询。",
  owner_party: "ORG_A",
  time_start: "2012-11-11T00:00:00",
  time_end: "2012-12-11T00:00:00",
  source_granularity: "30m",
  supported_query_types: ["SUM", "COUNT", "AVERAGE", "TIME_SERIES"],
  supported_group_by: ["30m", "1h", "1d"],
  privacy_protection: "家庭级贡献裁剪、秘密共享与分布式差分隐私。",
  raw_download_allowed: false,
  status: "ACTIVE",
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
};

function grant(status, suffix) {
  return {
    grant_id: `GRANT-${suffix}`,
    request_id: `REQUEST-${suffix}`,
    grantee_user_id: "analyst_demo",
    parties: ["ORG_A"],
    allowed_query_types: ["SUM"],
    allowed_start_time: "2012-11-11T00:00:00",
    allowed_end_time: "2012-11-12T00:00:00",
    allowed_group_by: [],
    max_epsilon_per_query: 1,
    total_epsilon_limit: 4,
    epsilon_consumed: 1,
    epsilon_reserved: 0,
    epsilon_remaining: 3,
    valid_from: "2026-01-01T00:00:00",
    expires_at: "2099-01-01T00:00:00",
    status,
    created_at: "2026-01-01T00:00:00",
    revoked_at: null,
  };
}

const policy = {
  authorization_enforcement_enabled: true,
  raw_download_allowed: false,
  calculation_mode: "DISTRIBUTED_DP",
  supported_query_types: ["SUM", "COUNT", "AVERAGE", "TIME_SERIES"],
  supported_group_by: ["30m", "1h", "1d"],
  default_total_epsilon: 20,
  session_ttl_seconds: 28800,
  audit_enabled: true,
  party_nodes: [
    { service_id: "party-a", name: "园区 A", online: true, latency_ms: 2, version: "0.4.0" },
  ],
  compute_nodes: [
    { service_id: "compute-s1", name: "计算节点 S1", online: true, latency_ms: 3, version: "0.4.0" },
    { service_id: "compute-s2", name: "计算节点 S2", online: false, latency_ms: 4, version: "0.4.0" },
  ],
};

const dataImport = {
  import_id: "IMPORT-000001",
  party_id: "ORG_A",
  uploader_user_id: "owner_a",
  original_filename: "snapshot.csv",
  source_sha256: "a".repeat(64),
  parquet_sha256: "b".repeat(64),
  file_size_bytes: 120,
  row_count: 10,
  valid_row_count: 10,
  invalid_row_count: 0,
  duplicate_count: 0,
  time_start: "2012-11-11T00:00:00",
  time_end: "2012-11-12T00:00:00",
  schema_version: "energy-v1",
  import_mode: "FULL_SNAPSHOT",
  status: "VALID",
  validation_summary: { schema_matches: true, error_count: 0, errors: [], errors_truncated: false },
  is_active: false,
  created_at: "2026-01-01T00:00:00",
  validation_started_at: "2026-01-01T00:00:01",
  validation_completed_at: "2026-01-01T00:00:02",
  activated_at: null,
  archived_at: null,
  error_message: null,
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

function setup(grants) {
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
    if (path === "/api/v1/auth/me") return json(owner);
    if (path === "/api/v1/grants/owner") return json(grants);
    if (path === "/api/v1/catalog/assets/owner") return json([asset]);
    if (path === "/api/v1/data-imports/mine") return json([dataImport]);
    if (path === "/api/v1/data-imports/active") return json({ party_id: "ORG_A", dataset_version: "BASELINE", row_count: 144000, time_start: "2012-11-11T00:00:00", time_end: "2012-12-10T23:30:00", activated_at: null, status: "ACTIVE", fallback_warning: null });
    if (path === "/api/v1/data-imports/config") return json({ enabled: true, import_mode: "FULL_SNAPSHOT", max_bytes: 52428800, max_rows: 500000, allowed_extensions: [".csv"], allowed_encodings: ["UTF-8", "UTF-8-SIG"], expected_columns: ["household_id", "organization_id", "timestamp", "energy_kwh"], unique_key: ["household_id", "timestamp"] });
    if (path === "/api/v1/data-imports/IMPORT-000001/activate") return json({ ...dataImport, status: "ACTIVE", is_active: true, activated_at: "2026-01-01T00:01:00" });
    if (path === "/api/v1/system/policy-summary") return json(policy);
    if (path.startsWith("/api/v1/tasks")) return json([]);
    if (path === "/api/v1/parties") return json([]);
    if (path === "/api/v1/system/health") return json({ services: [], checked_at: "2026-01-01T00:00:00" });
    if (path.startsWith("/api/v1/privacy/budgets")) return json({ total_epsilon: 20, used_epsilon: 0, reserved_epsilon: 0, remaining_epsilon: 20 });
    return json({ detail: `unexpected ${path}` }, 404);
  };
  return calls;
}

function clickPage(page) {
  const element = document.querySelector(`[data-page="${page}"]`);
  assert.ok(element, `menu entry not found: ${page}`);
  element.dispatchEvent(new MouseEvent("click", { bubbles: true }));
}

async function settle(ms = 150) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

test("owner pages use real scoped APIs and show honest system state", async () => {
  const calls = setup([
    grant("ACTIVE", "ACTIVE"),
    grant("EXPIRED", "EXPIRED"),
    grant("REVOKED", "REVOKED"),
    grant("EXHAUSTED", "EXHAUSTED"),
  ]);
  await import(`../src/main.js?owner-pages=${Date.now()}`);
  await settle();
  assert.doesNotMatch(document.querySelector(".topbar")?.textContent || "", /开发环境|测试环境|生产环境|环境未配置|环境状态未知/);
  assert.equal(document.querySelector(".topbar .env, .topbar .env-wrap"), null);
  assert.ok(!document.querySelector('[data-action="toggle-env"], [data-action="set-env"]'));

  clickPage("owner-grants");
  await settle();
  const grantText = document.querySelector("main.content")?.textContent || "";
  assert.match(grantText, /GRANT-ACTIVE/);
  assert.match(grantText, /analyst_demo/);
  for (const status of ["ACTIVE", "EXPIRED", "REVOKED", "EXHAUSTED"]) assert.match(grantText, new RegExp(status));
  const statusClasses = ["ACTIVE", "EXPIRED", "REVOKED", "EXHAUSTED"].map((status) =>
    Array.from(document.querySelectorAll("main.content .tag")).find((item) => item.textContent === status)?.className,
  );
  assert.equal(new Set(statusClasses).size, 4);
  assert.ok(!document.querySelector('[data-action="use-grant"]'));

  clickPage("data");
  await settle();
  const dataText = document.querySelector("main.content")?.textContent || "";
  assert.equal(document.querySelector("main.content h2 small"), null);
  assert.match(dataText, /本园区数据资产/);
  assert.match(dataText, /ENERGY_ORG_A/);
  assert.doesNotMatch(dataText, /ENERGY_ORG_B|储能示范站D|充电运营商E|工业企业F/);
  assert.doesNotMatch(dataText, /328万条|99\.4%|在线数据方|边缘节点 18/);
  assert.match(dataText, /CSV 安全导入|完整快照导入|IMPORT-000001|BASELINE/);
  assert.ok(document.querySelector("#csv-import-file"));
  assert.ok(document.querySelector('[data-action="activate-data-import"]'));
  assert.equal(document.querySelectorAll(".planned-methods button:disabled").length, 4);
  const ownerAssetCard = document.querySelector(".owner-asset-card");
  assert.ok(ownerAssetCard);
  assert.equal(ownerAssetCard.querySelectorAll(".asset-query-tag").length, 4);
  assert.deepEqual(Array.from(ownerAssetCard.querySelectorAll(".asset-query-tag"), (item) => item.textContent), ["SUM", "COUNT", "AVERAGE", "TIME_SERIES"]);
  assert.match(ownerAssetCard.textContent || "", /2012\/11\/11 — 2012\/12\/11/);
  assert.doesNotMatch(ownerAssetCard.textContent || "", /00:00:00|求和 SUM|计数 COUNT|均值 AVERAGE|时间序列 TIME_SERIES|原始下载|DISABLED|家庭级贡献裁剪/);
  ownerAssetCard.querySelector('[data-action="view-catalog-asset"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  assert.match(document.querySelector(".modal")?.textContent || "", /时序粒度|30m · 1h · 1d|保护机制|家庭级贡献裁剪/);
  document.querySelector('.modal [data-action="close-overlay"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  assert.doesNotMatch(dataText, /undefined|null|\[object Object\]/);
  globalThis.confirm = () => true;
  document.querySelector('[data-action="activate-data-import"]').dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await settle();
  assert.ok(calls.includes("/api/v1/data-imports/IMPORT-000001/activate"));

  clickPage("policy");
  await settle();
  const policyText = document.querySelector("main.content")?.textContent || "";
  assert.equal(document.querySelector("main.content h2 small"), null);
  assert.match(policyText, /授权强制校验/);
  assert.match(policyText, /DISTRIBUTED_DP/);
  assert.match(policyText, /暂无策略变更记录/);
  assert.match(policyText, /party-a|园区 A/);
  assert.doesNotMatch(policyText, /张伟|李娜|王强|陈磊|2025-06/);
  assert.ok(calls.includes("/api/v1/grants/owner"));
  assert.ok(calls.includes("/api/v1/catalog/assets/owner"));
  assert.ok(calls.includes("/api/v1/system/policy-summary"));
  assert.ok(!calls.some((path) => path.includes("party_id=")));
});

test("owner grants page shows a truthful empty state", async () => {
  setup([]);
  await import(`../src/main.js?owner-empty=${Date.now()}`);
  await settle();
  clickPage("owner-grants");
  await settle();
  assert.equal(document.querySelector("main.content h2 small"), null);
  assert.match(document.querySelector("main.content")?.textContent || "", /暂无本园区相关授权/);
});
