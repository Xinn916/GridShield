import { test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://127.0.0.1:8000";

const owner = { user_id: "owner_b", username: "owner_b", role: "DATA_OWNER", party_id: "ORG_B", is_active: true };
const approval = {
  approval_id: "APPROVAL-000001-ORG_B", request_id: "REQUEST-000001", party_id: "ORG_B",
  approver_user_id: null, decision: "PENDING", reason: null, allowed_query_types: null,
  allowed_start_time: null, allowed_end_time: null, allowed_group_by: null,
  max_epsilon_per_query: null, total_epsilon_limit: null, expires_at: null,
  decided_at: null, created_at: "2026-08-05T01:53:06",
};
const request = {
  request_id: "REQUEST-000001", requester_user_id: "analyst_demo", purpose: "跨园区用电趋势分析演示",
  requested_parties: ["ORG_A", "ORG_B"], requested_query_types: ["SUM"],
  requested_start_time: "2012-11-11T00:00:00", requested_end_time: "2012-11-13T00:00:00",
  requested_group_by: [], requested_max_epsilon_per_query: 2, requested_total_epsilon: 4,
  requested_expires_at: "2099-01-01T00:00:00", status: "PENDING",
  created_at: "2026-08-05T01:53:06", submitted_at: "2026-08-05T01:53:06",
  completed_at: null, rejection_reason: null, approvals: [approval],
};
let submittedDecision = null;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

function setup() {
  submittedDecision = null;
  const dom = new JSDOM("<!doctype html><html><body><div id='app'></div></body></html>", { url: "http://localhost:5173/", pretendToBeVisual: true });
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.HTMLElement = dom.window.HTMLElement;
  globalThis.Element = dom.window.Element;
  globalThis.Node = dom.window.Node;
  globalThis.MouseEvent = dom.window.MouseEvent;
  globalThis.Event = dom.window.Event;
  globalThis.fetch = async (url, options = {}) => {
    const path = String(url).replace("http://127.0.0.1:8000", "");
    if (path === "/api/v1/auth/me") return json(owner);
    if (path === "/api/v1/approvals/pending") return json([approval]);
    if (path === `/api/v1/approvals/${approval.approval_id}`) return json(approval);
    if (path === `/api/v1/access-requests/${request.request_id}`) return json(request);
    if (path === `/api/v1/approvals/${approval.approval_id}/decision` && options.method === "POST") {
      submittedDecision = JSON.parse(options.body);
      return json({ ...approval, ...submittedDecision, decision: submittedDecision.decision });
    }
    if (path.startsWith("/api/v1/tasks")) return json([]);
    if (path === "/api/v1/parties") return json([]);
    if (path === "/api/v1/system/health") return json({ services: [], checked_at: "2026-08-05T00:00:00" });
    if (path.startsWith("/api/v1/privacy/budgets")) return json({ total_epsilon: 20, used_epsilon: 0, reserved_epsilon: 0, remaining_epsilon: 20 });
    return json({ detail: `unexpected ${path}` }, 404);
  };
}

test("owner approval detail displays real request fields without undefined", async () => {
  setup();
  await import(`../src/main.js?approval-detail=${Date.now()}`);
  await new Promise((resolve) => setTimeout(resolve, 120));
  document.querySelector('[data-page="pending-approvals"]').dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await new Promise((resolve) => setTimeout(resolve, 140));
  document.querySelector('[data-action="view-approval"]').dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await new Promise((resolve) => setTimeout(resolve, 160));

  const text = document.querySelector("main.content")?.textContent || "";
  for (const expected of [
    "申请编号", "REQUEST-000001", "申请人", "analyst_demo", "使用目的", "跨园区用电趋势分析演示",
    "申请园区", "ORG_A / ORG_B", "查询类型", "SUM", "开始时间", "结束时间", "group_by",
    "单次 epsilon 上限", "累计 epsilon", "申请到期时间", "当前申请状态", "PENDING", "—",
  ]) assert.match(text, new RegExp(expected));
  assert.doesNotMatch(text, /undefined|null|\[object Object\]/);
  const allowedTypes = document.querySelector("#approval-types");
  const allowedTypesField = document.querySelector(".approval-types-field");
  assert.equal(allowedTypesField?.tagName, "DIV", "query type controls must not create nested label markup");
  assert.equal(allowedTypesField?.closest("label"), null);
  assert.ok(allowedTypes?.classList.contains("approval-types-readonly"));
  assert.equal(allowedTypes.querySelector(".query-type-pill")?.textContent, "SUM");
  assert.ok(!allowedTypes.querySelector('input[type="checkbox"]'), "a single query type must not look like a toggle");
  assert.match(allowedTypes.textContent, /本申请仅包含此查询类型/);

  document.querySelector("#approval-decision").value = "CONDITIONALLY_APPROVED";
  document.querySelector('[data-action="submit-approval-decision"]').dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await new Promise((resolve) => setTimeout(resolve, 100));
  assert.deepEqual(submittedDecision?.allowed_query_types, ["SUM"]);
  assert.equal(submittedDecision?.decision, "CONDITIONALLY_APPROVED");
  assert.ok(document.querySelector('[data-page="pending-approvals"].active'), "successful decision returns to pending approvals");
});
