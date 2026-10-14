import { test } from "node:test";
import assert from "node:assert/strict";

process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://127.0.0.1:8000";

import {
  PAGE_REGISTRY,
  featureForRoleById,
  grantConflicts,
  navItemsForRole,
  searchableFeaturesForRole,
  validateAccessRequest,
} from "../src/access/access-control-ui.js";
import { getCurrentUser, login, logout } from "../src/api/auth.js";
import { listCatalogAssets } from "../src/api/catalog.js";
import { createAccessRequest, submitAccessRequest } from "../src/api/access-requests.js";
import { decideApproval, listPendingApprovals } from "../src/api/approvals.js";
import { listMyGrants } from "../src/api/grants.js";


const grant = {
  grant_id: "GRANT-1",
  parties: ["ORG_A", "ORG_B"],
  allowed_query_types: ["SUM", "TIME_SERIES"],
  allowed_start_time: "2012-11-11T06:00:00Z",
  allowed_end_time: "2012-11-12T18:00:00Z",
  allowed_group_by: ["1h"],
  max_epsilon_per_query: 1,
  epsilon_remaining: 2.5,
};

test("sidebar and role-aware search share one real page registry", () => {
  const expected = {
    ANALYST: ["overview", "catalog", "my-requests", "new-request", "my-grants", "query", "compute", "report", "performance"],
    DATA_OWNER: ["overview", "pending-approvals", "approval-history", "owner-grants", "data", "policy"],
    AUDITOR: ["overview", "request-audit", "approval-audit", "grant-audit", "audit"],
    ADMIN: ["overview", "admin-requests", "admin-grants", "admin-users", "security-audit", "settings"],
  };
  for (const [role, ids] of Object.entries(expected)) {
    assert.deepEqual(navItemsForRole(role).map(([id]) => id), ids);
    assert.deepEqual(searchableFeaturesForRole(role).map((item) => item.id), ids);
  }
  assert.equal(featureForRoleById("ADMIN", "performance"), null);
  assert.equal(featureForRoleById("ANALYST", "performance")?.title, "性能测试");
  assert.equal(new Set(PAGE_REGISTRY.map((item) => item.id)).size, PAGE_REGISTRY.length);
  assert.ok(PAGE_REGISTRY.every((item) => item.id && item.title && item.icon && item.description && item.roles.length));
});


function validRequest() {
  return {
    purpose: "跨园区用电趋势分析",
    requested_parties: ["ORG_A", "ORG_B"],
    requested_query_types: ["SUM", "TIME_SERIES"],
    requested_start_time: "2012-11-11T00:00",
    requested_end_time: "2012-11-12T00:00",
    requested_group_by: ["1h"],
    requested_max_epsilon_per_query: 1,
    requested_total_epsilon: 4,
    requested_expires_at: "2099-01-01T00:00",
  };
}


test("backend role controls the visible navigation entries", () => {
  const analyst = navItemsForRole("ANALYST").map(([id]) => id);
  const owner = navItemsForRole("DATA_OWNER").map(([id]) => id);
  const auditor = navItemsForRole("AUDITOR").map(([id]) => id);
  const admin = navItemsForRole("ADMIN").map(([id]) => id);
  assert.ok(analyst.includes("catalog") && analyst.includes("query") && analyst.includes("performance"));
  assert.equal(analyst.at(-1), "performance");
  assert.ok(!analyst.includes("pending-approvals"));
  assert.ok(owner.includes("pending-approvals") && owner.includes("owner-grants"));
  assert.ok(!owner.includes("query"));
  assert.ok(!owner.includes("performance") && !auditor.includes("performance") && !admin.includes("performance"));
  assert.ok(auditor.includes("request-audit") && auditor.includes("audit"));
  assert.ok(admin.includes("admin-users") && admin.includes("admin-grants"));
});


test("new access request validation catches required scope rules", () => {
  assert.equal(validateAccessRequest(validRequest()), null);
  assert.match(validateAccessRequest({ ...validRequest(), purpose: "短" }), /用途/);
  assert.match(validateAccessRequest({ ...validRequest(), requested_parties: [] }), /园区/);
  assert.match(
    validateAccessRequest({ ...validRequest(), requested_end_time: "2012-11-10T00:00" }),
    /早于/,
  );
  assert.match(
    validateAccessRequest({ ...validRequest(), requested_max_epsilon_per_query: 6 }),
    /不超过 5/,
  );
  assert.match(
    validateAccessRequest({ ...validRequest(), requested_group_by: [] }),
    /时序粒度/,
  );
  assert.match(
    validateAccessRequest({ ...validRequest(), requested_expires_at: "2020-01-01T00:00" }),
    /到期时间/,
  );
});


test("authorization query helper reports every grant boundary conflict", () => {
  const base = {
    grant_id: grant.grant_id,
    parties: ["ORG_A"],
    query_type: "SUM",
    start_time: "2012-11-11T06:00:00Z",
    end_time: "2012-11-12T00:00:00Z",
    group_by: null,
    epsilon: 1,
  };
  assert.deepEqual(grantConflicts(base, [grant]), []);
  assert.match(grantConflicts({ ...base, grant_id: "OTHER" }, [grant])[0], /有效授权/);
  assert.match(grantConflicts({ ...base, parties: ["ORG_C"] }, [grant])[0], /园区/);
  assert.match(grantConflicts({ ...base, query_type: "COUNT" }, [grant])[0], /查询类型/);
  assert.match(grantConflicts({ ...base, start_time: "2012-11-11T00:00:00Z" }, [grant])[0], /时间/);
  assert.match(
    grantConflicts({ ...base, query_type: "TIME_SERIES", group_by: "30m" }, [grant])[0],
    /30 分钟.*1 小时/,
  );
  assert.match(grantConflicts({ ...base, epsilon: 1.1 }, [grant])[0], /epsilon/);
});


test("auth, catalog, request, approval and grant clients use session cookies and expected endpoints", async () => {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url: String(url), options });
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  await login("analyst_demo", "not-stored-in-frontend");
  await getCurrentUser();
  await listCatalogAssets();
  await createAccessRequest(validRequest());
  await submitAccessRequest("REQUEST-1");
  await listPendingApprovals();
  await decideApproval("APPROVAL-1", { decision: "APPROVED" });
  await listMyGrants();
  await logout();

  assert.ok(calls.every((call) => call.options.credentials === "include"));
  assert.deepEqual(
    calls.map((call) => new URL(call.url).pathname),
    [
      "/api/v1/auth/login",
      "/api/v1/auth/me",
      "/api/v1/catalog/assets",
      "/api/v1/access-requests",
      "/api/v1/access-requests/REQUEST-1/submit",
      "/api/v1/approvals/pending",
      "/api/v1/approvals/APPROVAL-1/decision",
      "/api/v1/grants/mine",
      "/api/v1/auth/logout",
    ],
  );
  assert.equal(calls[0].options.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    username: "analyst_demo",
    password: "not-stored-in-frontend",
  });
});


test("401 and 403 responses remain visible to the UI error layer", async () => {
  let status = 401;
  globalThis.fetch = async () =>
    new Response(JSON.stringify({ detail: status === 401 ? "请先登录" : "当前角色无权审批" }), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  await assert.rejects(getCurrentUser(), (error) => error.status === 401 && /登录/.test(error.message));
  status = 403;
  await assert.rejects(listPendingApprovals(), (error) => error.status === 403 && /无权/.test(error.message));
});
