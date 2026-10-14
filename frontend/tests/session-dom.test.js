import { test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://127.0.0.1:8000";

test("refresh restores a backend owner session, applies role menu, and logout returns to login", async () => {
  const dom = new JSDOM(
    "<!doctype html><html><body><div id='app'></div></body></html>",
    { url: "http://localhost:5173/", pretendToBeVisual: true },
  );
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.HTMLElement = dom.window.HTMLElement;
  globalThis.Element = dom.window.Element;
  globalThis.Node = dom.window.Node;
  globalThis.MouseEvent = dom.window.MouseEvent;
  globalThis.Event = dom.window.Event;
  globalThis.fetch = async (url) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    if (path === "/api/v1/auth/me") {
      return new Response(JSON.stringify({
        user_id: "owner_b",
        username: "owner_b",
        role: "DATA_OWNER",
        party_id: "ORG_B",
        is_active: true,
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (path === "/api/v1/auth/logout") return new Response(null, { status: 204 });
    return new Response(JSON.stringify({}), { status: 200, headers: { "Content-Type": "application/json" } });
  };

  await import(`../src/main.js?session=${Date.now()}`);
  await new Promise((resolve) => setTimeout(resolve, 100));
  assert.match(document.querySelector(".topbar")?.textContent || "", /owner_b/);
  document.querySelector('[data-action="toggle-user"]').dispatchEvent(new MouseEvent("click", { bubbles: true }));
  assert.match(document.body.textContent || "", /ORG_B/);
  assert.ok(document.querySelector('[data-page="pending-approvals"]'));
  assert.ok(!document.querySelector('[data-page="query"]'));

  document.querySelector('[data-action="logout"]').dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await new Promise((resolve) => setTimeout(resolve, 80));
  assert.ok(document.querySelector(".login-page"));
});
