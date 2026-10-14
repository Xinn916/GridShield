import { afterEach, test } from "node:test";
import assert from "node:assert/strict";

process.env.VITE_USE_MOCK = "false";
process.env.VITE_API_BASE_URL = "http://backend.test:8000";

const { request, ApiError } = await import("../src/api/client.js");

function installFetch(handler) {
  globalThis.fetch = handler;
}

afterEach(() => {
  delete globalThis.fetch;
});

test("API client uses the configured baseURL", async () => {
  let calledUrl = null;
  installFetch(async (url) => {
    calledUrl = String(url);
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  await request("/api/v1/parties");
  assert.equal(calledUrl, "http://backend.test:8000/api/v1/parties");
});

test("API client does not duplicate the prefix when baseURL is /api", async () => {
  process.env.VITE_API_BASE_URL = "/api";
  let calledUrl = null;
  installFetch(async (url) => {
    calledUrl = String(url);
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  await request("/api/v1/parties");
  assert.equal(calledUrl, "/api/v1/parties");
  process.env.VITE_API_BASE_URL = "http://backend.test:8000";
});

test("API client serializes POST body as JSON", async () => {
  let seen = null;
  installFetch(async (url, options) => {
    seen = { url: String(url), method: options.method, body: options.body, headers: options.headers };
    return new Response(JSON.stringify({ task_id: "TASK-1" }), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });
  });
  const payload = { query_type: "SUM", parties: ["ORG_A"], epsilon: 1.0 };
  const data = await request("/api/v1/tasks", { method: "POST", body: payload });
  assert.equal(seen.url, "http://backend.test:8000/api/v1/tasks");
  assert.equal(seen.method, "POST");
  assert.equal(JSON.parse(seen.body).query_type, "SUM");
  assert.match(seen.headers["Content-Type"], /application\/json/);
  assert.equal(data.task_id, "TASK-1");
});

test("API client forwards FormData without forcing a JSON content type", async () => {
  let seen = null;
  installFetch(async (url, options) => {
    seen = { url: String(url), body: options.body, headers: options.headers };
    return new Response(JSON.stringify({ import_id: "IMPORT-000001" }), { status: 201 });
  });
  const form = new FormData();
  form.append("file", new Blob(["a,b\n1,2\n"], { type: "text/csv" }), "snapshot.csv");
  await request("/api/v1/data-imports", { method: "POST", body: form });
  assert.equal(seen.url, "http://backend.test:8000/api/v1/data-imports");
  assert.equal(seen.body, form);
  assert.equal(seen.headers["Content-Type"], undefined);
});

test("HTTP error is parsed into ApiError with detail", async () => {
  installFetch(async () =>
    new Response(JSON.stringify({ detail: "insufficient privacy budget" }), {
      status: 409,
      headers: { "Content-Type": "application/json" },
    })
  );
  await assert.rejects(
    request("/api/v1/tasks", { method: "POST", body: {} }),
    (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 409);
      assert.equal(error.message, "insufficient privacy budget");
      return true;
    }
  );
});

test("HTML 502 response is replaced with a safe HTTP error", async () => {
  installFetch(async () =>
    new Response("<!doctype html><html><title>502 Bad Gateway</title><body>nginx</body></html>", {
      status: 502,
      statusText: "Bad Gateway",
      headers: { "Content-Type": "text/html" },
    })
  );
  await assert.rejects(
    request("/api/v1/approvals/history"),
    (error) => {
      assert.equal(error.message, "HTTP 502 Bad Gateway");
      assert.doesNotMatch(error.message, /<html|<body|doctype|\[object Object\]/i);
      return true;
    },
  );
});

test("network error is reported as network error, never fallback to mock", async () => {
  installFetch(async () => {
    throw new TypeError("fetch failed");
  });
  await assert.rejects(
    request("/api/v1/parties"),
    (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.networkError, true);
      assert.match(error.message, /网络错误/);
      return true;
    }
  );
});

test("request timeout is reported with timedOut flag", async () => {
  installFetch((url, options) =>
    new Promise((resolve, reject) => {
      options.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    })
  );
  await assert.rejects(
    request("/api/v1/tasks/TASK-1", { timeout: 20 }),
    (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.timedOut, true);
      assert.equal(error.code, "TIMEOUT");
      return true;
    }
  );
});

test("external AbortController cancels the request", async () => {
  installFetch((url, options) =>
    new Promise((resolve, reject) => {
      options.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    })
  );
  const controller = new AbortController();
  const pending = request("/api/v1/tasks/TASK-1", { signal: controller.signal });
  controller.abort();
  await assert.rejects(pending, (error) => {
    assert.equal(error.code, "ABORTED");
    return true;
  });
});

test("mock mode must be explicitly enabled, otherwise client rejects", async () => {
  process.env.VITE_USE_MOCK = "true";
  try {
    await assert.rejects(request("/api/v1/parties"), (error) => {
      assert.equal(error.code, "MOCK_ENABLED");
      return true;
    });
  } finally {
    process.env.VITE_USE_MOCK = "false";
  }
});
