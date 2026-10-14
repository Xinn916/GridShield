import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("query workbench uses one card with a bounded chat and an independent sticky task column", async () => {
  const css = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");

  assert.match(css, /\.agent-workbench-card\s*\{[^}]*margin-bottom:\s*18px;[^}]*overflow:\s*visible;/);
  assert.match(css, /\.agent-workbench\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0, 2fr\) minmax\(340px, \.85fr\);[\s\S]*?align-items:\s*start;[\s\S]*?gap:\s*18px;[\s\S]*?min-width:\s*0;/);
  assert.match(css, /\.agent-main-column\s*\{[^}]*display:\s*flex;[^}]*min-width:\s*0;[^}]*min-height:\s*0;[^}]*flex-direction:\s*column;/);
  assert.match(css, /\.agent-conversation\s*\{[\s\S]*?height:\s*clamp\(380px, 43vh, 440px\);[\s\S]*?min-height:\s*0;[\s\S]*?overflow-y:\s*auto;[\s\S]*?scrollbar-gutter:\s*stable;/);
  assert.match(css, /\.agent-composer\s*\{[^}]*flex:\s*0 0 auto;/);
  assert.match(css, /\.current-task-column\s*\{[\s\S]*?position:\s*sticky;[\s\S]*?top:\s*16px;[\s\S]*?align-self:\s*start;[\s\S]*?border-left:/);
  assert.match(css, /\.current-task-column:has\(\.task-editor:not\(\[hidden\]\)\) \.current-task-summary\s*\{\s*display:\s*none;/);
  assert.doesNotMatch(css, /\.task-editor\s*\{[^}]*max-height:/);
  assert.doesNotMatch(css, /\.agent-workbench\s*\{[^}]*(?:height:\s*100%|align-items:\s*stretch|grid-auto-rows)/);
  assert.doesNotMatch(css, /\.query-workbench-grid/);
  assert.match(css, /@media \(max-width:\s*1080px\)\s*\{[\s\S]*?\.agent-workbench\s*\{\s*grid-template-columns:\s*1fr;/);
});

test("history conversation items override global button sizing and keep text separated", async () => {
  const css = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");

  assert.match(css, /\.agent-history-group\s*\{[^}]*display:\s*grid;[^}]*gap:\s*8px;/);
  assert.match(css, /\.agent-history-item\s*\{[\s\S]*?display:\s*flex;[\s\S]*?height:\s*auto;[\s\S]*?min-height:\s*78px;[\s\S]*?justify-content:\s*flex-start;[\s\S]*?flex-direction:\s*column;/);
  assert.match(css, /\.agent-history-item strong\s*\{[^}]*line-height:\s*1\.4;[^}]*text-align:\s*left;/);
  assert.match(css, /\.agent-history-item > span\s*\{[^}]*line-height:\s*1\.45;[^}]*text-align:\s*left;/);
  assert.match(css, /\.agent-history-item small\s*\{[^}]*justify-content:\s*space-between;[^}]*line-height:\s*1\.35;/);
});

test("speech input stays compact beside the send button", async () => {
  const css = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");

  assert.match(css, /\.agent-composer \.query-input input\s*\{\s*min-width:\s*0;/);
  assert.match(css, /\.agent-composer \.query-input \.speech-input-button\s*\{[\s\S]*?flex:\s*0 0 32px;[\s\S]*?width:\s*32px;[\s\S]*?background:\s*#f5f9ff;/);
  assert.match(css, /\.speech-input-button\.listening\s*\{[\s\S]*?animation:\s*speech-listening-pulse/);
  assert.doesNotMatch(css, /\.speech-input-button\s*\{[^}]*position:\s*absolute/);
});
