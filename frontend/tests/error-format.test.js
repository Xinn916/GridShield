import { test } from "node:test";
import assert from "node:assert/strict";
import { formatApiError } from "../src/utils/errors.js";

test("formatApiError handles strings, message and detail", () => {
  assert.equal(formatApiError("连接失败"), "连接失败");
  assert.equal(formatApiError({ message: "会话已过期" }), "会话已过期");
  assert.equal(formatApiError({ detail: "没有审批权限" }), "没有审批权限");
});

test("formatApiError joins validation detail arrays readably", () => {
  const error = {
    detail: [
      { loc: ["body", "reason"], msg: "字段不能为空", type: "missing" },
      { loc: ["body", "epsilon"], msg: "必须大于 0", type: "value_error" },
    ],
  };
  assert.equal(formatApiError(error), "reason：字段不能为空；epsilon：必须大于 0");
});

test("formatApiError prefers response data and never stringifies arbitrary objects", () => {
  assert.equal(
    formatApiError({ message: "outer", response: { data: { detail: "服务拒绝请求" } } }),
    "服务拒绝请求",
  );
  assert.equal(formatApiError({ response: { data: { message: "网关不可用" } } }), "网关不可用");
  for (const error of [{}, { detail: {} }, { unexpected: [1, 2] }, null, undefined]) {
    const text = formatApiError(error);
    assert.equal(text, "请求失败，请稍后重试");
    assert.doesNotMatch(text, /\[object Object\]|undefined|null|NaN/);
  }
});

test("formatApiError rejects raw HTML error pages", () => {
  const text = formatApiError("<!doctype html><html><title>502 Bad Gateway</title></html>");
  assert.equal(text, "请求失败，请稍后重试");
  assert.doesNotMatch(text, /<html|<title|doctype/i);
});
