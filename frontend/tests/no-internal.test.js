import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";

const files = [
  "src/query/query-controller.js",
  "src/api/client.js",
  "src/api/tasks.js",
  "src/api/parties.js",
  "src/api/privacy.js",
  "src/api/audit.js",
  "src/api/system.js",
];

test("query modules never reference mock data", async () => {
  for (const file of files) {
    const source = await readFile(new URL(`../${file}`, import.meta.url), "utf8");
    assert.ok(!source.includes("mockData"), `${file} must not reference mockData`);
  }
});

test("frontend modules never call un-noised internal endpoints", async () => {
  for (const file of files) {
    const source = await readFile(new URL(`../${file}`, import.meta.url), "utf8");
    assert.ok(!source.includes("/internal/statistics"), `${file} must not call party internal statistics`);
    assert.ok(!source.includes("/internal/tasks/"), `${file} must not call compute share endpoints`);
    assert.ok(!source.includes("partial_noise"), `${file} must not request partial noise`);
  }
});
