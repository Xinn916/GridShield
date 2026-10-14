import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";

process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://127.0.0.1:8000";

const admin = {
  user_id: "admin_demo",
  username: "admin_demo",
  role: "ADMIN",
  party_id: null,
  is_active: true,
};

const overview = {
  database: {
    type: "SQLite",
    connected: true,
    demo_database: true,
    note: "当前为单机演示数据库，适用于本地原型和低并发运行；生产环境建议使用 PostgreSQL。",
  },
  asset_storage: { type: "Parquet", party_count: 3, mount_mode: "READ_ONLY" },
  frontend_gateway: { service_id: "frontend", name: "前端网关 Nginx", online: true, latency_ms: 2, version: null },
  party_nodes: ["a", "b", "c"].map((suffix, index) => ({
    service_id: `party-${suffix}`,
    name: `园区 ${suffix.toUpperCase()}`,
    online: index !== 1,
    latency_ms: index + 3,
    version: "0.4.0",
  })),
  compute_nodes: [1, 2].map((index) => ({
    service_id: `compute-s${index}`,
    name: `计算节点 S${index}`,
    online: true,
    latency_ms: index + 5,
    version: "0.4.0",
  })),
  agent_model_configured: false,
  security_baseline: {
    authorization_enforcement_enabled: true,
    raw_download_disabled: true,
    session_cookie_http_only: true,
    cookie_samesite: "Lax",
    session_ttl_seconds: 28800,
    password_hash_storage: true,
    session_token_hash_storage: true,
    audit_enabled: true,
    calculation_mode: "DISTRIBUTED_DP",
    demo_identity_mode_enabled: true,
    did_wallet_verification: false,
    mfa_enabled: false,
    ip_allowlist_enabled: false,
    certificate_management: "DEPLOYMENT_MANAGED",
    https_forced: false,
  },
  planned_extensions: ["PostgreSQL", "Redis", "MQTT", "对象存储", "通知服务"].map((name) => ({ name, status: "PLANNED" })),
  maintenance_records: [],
  system_events: [{
    audit_id: 1,
    event_type: "LOGIN_SUCCESS",
    actor_user_id: "admin_demo",
    actor_role: "ADMIN",
    party_id: null,
    request_id: null,
    grant_id: null,
    task_id: null,
    decision: "ALLOWED",
    reason: null,
    timestamp: "2026-08-02T12:00:00Z",
  }],
  checked_at: "2026-08-02T12:00:00Z",
};

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
    if (path === "/api/v1/auth/me") return json(admin);
    if (path === "/api/v1/admin/system-overview") return json(overview);
    if (path.startsWith("/api/v1/tasks")) return json([]);
    if (path === "/api/v1/parties") return json([]);
    if (path === "/api/v1/system/health") return json({ services: [], checked_at: overview.checked_at });
    if (path.startsWith("/api/v1/privacy/budgets")) return json({ total_epsilon: 20, used_epsilon: 0, reserved_epsilon: 0, remaining_epsilon: 20 });
    return json({ detail: `unexpected ${path}` }, 404);
  };
  return calls;
}

async function openSettings() {
  const calls = setup();
  await import(`../src/main.js?admin-settings=${Date.now()}`);
  await new Promise((resolve) => setTimeout(resolve, 120));
  const menu = document.querySelector('[data-page="settings"]');
  assert.ok(menu, "admin settings menu should exist");
  menu.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await new Promise((resolve) => setTimeout(resolve, 160));
  return { calls, main: document.querySelector("main.content") };
}

test("admin settings page shows only real read-only dependencies and audit events", async () => {
  const { calls, main } = await openSettings();
  const text = main?.textContent || "";
  assert.equal(main?.querySelector("h2 small"), null);

  for (const expected of [
    "当前系统依赖与运行状态", "SQLite", "Parquet", "3 个数据方", "前端网关 Nginx",
    "party-a", "party-b", "party-c", "compute-s1", "compute-s2", "Agent 模型服务",
    "当前生效安全基线", "访问控制", "会话安全", "平台安全", "Cookie SameSite", "哈希存储", "账号初始化策略",
    "双因素认证", "未启用", "由部署环境配置", "运行状态摘要", "在线节点", "最近安全审计",
    "LOGIN_SUCCESS", "admin_demo", "暂无系统维护记录",
  ]) assert.match(text, new RegExp(expected));

  assert.ok(main.querySelector(".settings-layout"));
  assert.equal(main.querySelectorAll(".settings-main-column > .panel").length, 2);
  assert.equal(main.querySelectorAll(".settings-side-column > .panel").length, 3);
  assert.equal(main.querySelectorAll(".settings-security-group").length, 3);
  assert.equal(main.querySelectorAll(".integration-item").length, 0);
  assert.ok(calls.includes("/api/v1/admin/system-overview"));
  assert.equal(main.querySelectorAll("input, select").length, 0);
  assert.equal(main.querySelectorAll('[data-action="test-integration"], [data-action="edit-integration"], [data-action="save-settings"]').length, 0);

  assert.doesNotMatch(text, /MySQL 主数据库|10\.10\.0\.|oss:\/\/|smtp\.|sms\.aliyun|张伟|2025-06|自动备份成功|证书更新|服务重启/);
  assert.doesNotMatch(text, /DID|钱包/);
  assert.doesNotMatch(text, /规划中的生产扩展|未接入\s*\/\s*规划功能|PostgreSQL|Redis|MQTT|对象存储|通知服务|即将上线|规划中/);
  assert.doesNotMatch(text, /Redis 缓存.*已连接|MQTT Broker.*已连接|对象存储 OSS.*已连接/);
});

test("admin settings layout keeps columns and cards independently sized", () => {
  const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
  assert.match(css, /\.settings-layout\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1\.4fr\)\s+minmax\(320px,\s*\.8fr\);[\s\S]*?align-items:\s*start;/);
  assert.match(css, /\.settings-main-column,\s*\n\.settings-side-column\s*\{[\s\S]*?display:\s*flex;[\s\S]*?gap:\s*20px;/);
  assert.match(css, /@media\s*\(max-width:\s*1100px\)[\s\S]*?\.settings-layout\s*\{\s*grid-template-columns:\s*1fr;\s*\}/);
  assert.doesNotMatch(css, /\.settings-layout[^}]*height:\s*100%/);
});

test("expanded sidebar navigation is left aligned", () => {
  const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
  assert.match(css, /\.sidebar nav button\s*\{[^}]*justify-content:\s*flex-start/s);
  assert.match(css, /\.sidebar\.collapsed nav button\s*\{[^}]*justify-content:\s*center/s);
});
