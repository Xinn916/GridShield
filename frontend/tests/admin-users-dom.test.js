import { test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://127.0.0.1:8000";

const users = [
  { user_id: "admin_demo", username: "admin_demo", role: "ADMIN", party_id: null, is_active: true, created_at: "2026-08-01T00:00:00Z", last_login_at: "2026-08-16T08:00:00Z" },
  { user_id: "owner_a", username: "owner_a", role: "DATA_OWNER", party_id: "ORG_A", is_active: true, created_at: "2026-08-01T00:00:00Z", last_login_at: null },
  { user_id: "analyst_demo", username: "analyst_demo", role: "ANALYST", party_id: null, is_active: false, created_at: "2026-08-01T00:00:00Z", last_login_at: null },
];

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

async function openPage() {
  const dom = new JSDOM("<!doctype html><html><body><div id='app'></div></body></html>", { url: "http://localhost:5173/", pretendToBeVisual: true });
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.HTMLElement = dom.window.HTMLElement;
  globalThis.Element = dom.window.Element;
  globalThis.Node = dom.window.Node;
  globalThis.MouseEvent = dom.window.MouseEvent;
  globalThis.Event = dom.window.Event;
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    calls.push({ path, options });
    if (path === "/api/v1/auth/me") return json(users[0]);
    if (path === "/api/v1/admin/users") return json(users);
    return json({ detail: `unexpected ${path}` }, 404);
  };
  await import(`../src/main.js?admin-users=${Date.now()}`);
  await new Promise((resolve) => setTimeout(resolve, 100));
  document.querySelector('[data-page="admin-users"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await new Promise((resolve) => setTimeout(resolve, 100));
  return { calls, dom };
}

test("admin account page uses official wording and exposes account controls", async () => {
  const { dom } = await openPage();
  const main = dom.window.document.querySelector("main.content");
  assert.match(main.textContent, /账号与权限/);
  assert.doesNotMatch(main.textContent, /开发账号状态|预置账号/);
  assert.ok(main.querySelector("#admin-user-search"));
  assert.ok(main.querySelector('[data-action="create-admin-user"]'));
  assert.match(main.textContent, /最近登录/);
  assert.match(main.textContent, /创建时间/);
  assert.ok(main.querySelector('[data-action="reset-admin-password"]'));
  assert.ok(main.querySelector('[data-action="revoke-admin-sessions"]'));
});

test("admin account create modal validates role and organization binding", async () => {
  const { dom } = await openPage();
  const create = dom.window.document.querySelector('[data-action="create-admin-user"]');
  create.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await new Promise((resolve) => setTimeout(resolve, 30));
  const modal = dom.window.document.querySelector(".modal");
  assert.match(modal.textContent, /新建账号/);
  const role = modal.querySelector("#admin-user-role");
  role.value = "DATA_OWNER";
  role.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  assert.equal(modal.querySelector("#admin-user-org").disabled, false);
  assert.equal(modal.querySelector("#admin-user-org").required, true);
});

