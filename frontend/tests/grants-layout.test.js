import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("grant query action stays inside a locally scrollable table column", async () => {
  const [source, css] = await Promise.all([
    readFile(new URL("../src/main.js", import.meta.url), "utf8"),
    readFile(new URL("../src/styles.css", import.meta.url), "utf8"),
  ]);

  assert.match(source, /class="primary grant-use-button" data-action="use-grant"/);
  assert.match(source, /<div class="grants-table-wrap">\$\{table\(columns, rows, tableClass\)\}<\/div>/);
  assert.match(css, /\.grants-table-wrap\s*\{[^}]*max-width:\s*100%;[^}]*overflow-x:\s*auto;/);
  assert.match(css, /\.grants-table-action td:last-child\s*\{[^}]*position:\s*sticky;[^}]*right:\s*0;[^}]*width:\s*128px;/);
  assert.match(css, /\.grant-use-button\s*\{[^}]*width:\s*112px;[^}]*max-width:\s*100%;[^}]*white-space:\s*nowrap;/);
});
