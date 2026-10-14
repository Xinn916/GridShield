import { test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://127.0.0.1:8000";

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

function setupDom(fetchImpl) {
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
  globalThis.fetch = fetchImpl;
}

async function settle(ms = 140) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

test("login is credential-only and backend session determines owner role and party", async () => {
  let authenticated = false;
  let meCalls = 0;
  setupDom(async (url) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    if (path === "/api/v1/public/config") return json({ app_env: "development" });
    if (path === "/api/v1/auth/login") {
      authenticated = true;
      return json({ user_id: "ignored", username: "ignored", role: "ANALYST", party_id: null, is_active: true });
    }
    if (path === "/api/v1/auth/me") {
      meCalls += 1;
      return authenticated
        ? json({ user_id: "owner_b", username: "owner_b", role: "DATA_OWNER", party_id: "ORG_B", is_active: true })
        : json({ detail: "请先登录" }, 401);
    }
    if (path.startsWith("/api/v1/")) return json([]);
    return json({}, 404);
  });

  await import(`../src/main.js?login-product=${Date.now()}`);
  await settle();
  const loginText = document.querySelector(".login-page")?.textContent || "";
  assert.match(loginText, /身份认证/);
  assert.doesNotMatch(loginText, /演示账号|analyst_demo|owner_a|DID|钱包|选择.*角色/);
  assert.ok(document.querySelector("#login-username"));
  assert.ok(document.querySelector("#login-password"));
  assert.ok(!document.querySelector("select, [data-role], .did-item"));
  assert.doesNotMatch(loginText, /原始数据留存于数据提供方本地|秘密共享与分布式差分隐私协同保护|自然语言查询与授权约束协同执行/);
  assert.match(loginText, /数据不出域/);
  assert.match(loginText, /多方安全计算/);
  assert.match(loginText, /智能可信交互/);
  assert.equal(document.querySelectorAll(".login-feature").length, 3);

  document.querySelector("#login-username").value = "owner_b";
  document.querySelector("#login-password").value = "secret";
  document.querySelector("#login-form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await settle(220);

  assert.ok(meCalls >= 2, "current user must be read before and after login");
  assert.match(document.querySelector(".topbar")?.textContent || "", /owner_b/);
  document.querySelector('[data-action="toggle-user"]').dispatchEvent(new MouseEvent("click", { bubbles: true }));
  assert.match(document.body.textContent || "", /园区管理员 · ORG_B/);
  assert.ok(document.querySelector('[data-page="pending-approvals"]'));
  assert.ok(!document.querySelector('[data-page="query"]'));
  assert.equal(document.querySelector(".env, .env-wrap, .login-env"), null);
  assert.ok(!document.querySelector('[data-action="toggle-env"], [data-action="set-env"]'));
});

test("login hides environment metadata and renders backend login errors truthfully", async () => {
  setupDom(async (url) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    if (path === "/api/v1/public/config") return json({ app_env: "production" });
    if (path === "/api/v1/auth/me") return json({ detail: "请先登录" }, 401);
    if (path === "/api/v1/auth/login") return json({ detail: "用户名或密码错误" }, 401);
    return json({}, 404);
  });

  await import(`../src/main.js?login-error=${Date.now()}`);
  await settle();
  assert.equal(document.querySelector(".login-page .env, .login-env"), null);
  assert.doesNotMatch(document.querySelector(".login-page")?.textContent || "", /开发环境|测试环境|生产环境|环境未配置|环境状态未知/);
  document.querySelector("#login-username").value = "unknown";
  document.querySelector("#login-password").value = "wrong";
  document.querySelector("#login-form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await settle(180);
  assert.match(document.querySelector("[role='alert']")?.textContent || "", /用户名或密码错误/);
});

test("runtime config availability never creates a user-facing environment badge", async () => {
  setupDom(async (url) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    if (path === "/api/v1/public/config") return json({ detail: "temporarily unavailable" }, 503);
    if (path === "/api/v1/auth/me") return json({ detail: "请先登录" }, 401);
    return json({}, 404);
  });

  await import(`../src/main.js?runtime-config-unknown=${Date.now()}`);
  await settle();
  assert.equal(document.querySelector(".env, .env-wrap, .login-env"), null);
  assert.doesNotMatch(document.body.textContent || "", /开发环境|测试环境|生产环境|环境未配置|环境状态未知/);
});
