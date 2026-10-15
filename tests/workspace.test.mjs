import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const source = await readFile(new URL("../src/workspace/workspace-engine.js", import.meta.url), "utf8");
const scope = { window: {}, TextEncoder, Uint8Array, Uint32Array, DataView };
vm.createContext(scope);
vm.runInContext(source, scope);
const engine = scope.window.KodexWorkspaceEngine;

test("project paths are normalized and traversal or absolute paths are rejected", () => {
  assert.equal(engine.normalizeProjectPath("./src/app.js"), "src/app.js");
  assert.equal(engine.normalizeProjectPath("src\\app.js"), "src/app.js");
  assert.throws(() => engine.normalizeProjectPath("../outside.txt"), /relativo|inválida/i);
  assert.throws(() => engine.normalizeProjectPath("/etc/passwd"), /relativo/i);
  assert.throws(() => engine.normalizeProjectPath("C:\\secrets.txt"), /relativo/i);
  assert.throws(() => engine.normalizeProjectPath("src//app.js"), /inválida/i);
});

test("starter project contains real HTML, CSS, JavaScript, and documentation files", () => {
  const files = engine.createStarterProject();
  assert.match(files["index.html"], /<!doctype html>/i);
  assert.match(files["index.html"], /styles\.css/);
  assert.match(files["index.html"], /app\.js/);
  assert.match(files["styles.css"], /\.card/);
  assert.match(files["app.js"], /addEventListener/);
  assert.match(files["README.md"], /armazenamento local/i);
  const report = engine.validateProject(files);
  assert.equal(report.failed, 0);
});

test("static validation flags malformed JSON and classic JavaScript syntax", () => {
  const report = engine.validateProject({
    "settings.json": "{ broken }",
    "script.js": "function {",
    "index.html": "<html><body>Test</body></html>"
  });
  assert.ok(report.checks.some(check => check.status === "fail" && check.id === "json:settings.json"));
  assert.ok(report.checks.some(check => check.status === "fail" && check.id === "js:script.js"));
  assert.equal(report.failed, 2);
});

test("module syntax is reported as a warning rather than falsely marked as verified", () => {
  const report = engine.validateProject({ "script.mjs": "export const value = 1;" });
  assert.ok(report.checks.some(check => check.id === "js:script.mjs" && check.status === "warn"));
  assert.equal(report.failed, 0);
});

test("ZIP export includes valid local-file, central-directory, and end records", () => {
  const zip = engine.buildProjectZip({
    "index.html": "<h1>Olá</h1>",
    "src/main.js": "console.log('ok')"
  });
  const signature = bytes => Array.from(bytes.slice(0, 4)).map(byte => byte.toString(16).padStart(2, "0")).join("");
  assert.equal(signature(zip), "504b0304");
  assert.equal(signature(zip.slice(-22, -18)), "504b0506");
  const archiveText = new TextDecoder().decode(zip);
  assert.ok(archiveText.includes("index.html"));
  assert.ok(archiveText.includes("src/main.js"));
});

test("preview embeds project assets and blocks network connections with CSP", () => {
  const html = engine.buildPreviewHtml({
    "index.html": '<!doctype html><html><head><link rel="stylesheet" href="./styles.css"></head><body><button id="b">Run</button><script src="./app.js"></script></body></html>',
    "styles.css": "button { color: red; }",
    "app.js": 'document.querySelector("#b").textContent = "Ready";'
  });
  assert.match(html, /connect-src 'none'/);
  assert.match(html, /button \{ color: red; \}/);
  assert.match(html, /document\.querySelector/);
  assert.doesNotMatch(html, /src="\.\/app\.js"/);
  assert.throws(() => engine.buildPreviewHtml({ "README.md": "no html" }), /index\.html/);
});

test("project count and size limits are explicit", () => {
  const files = engine.createStarterProject();
  const report = engine.validateProject(files);
  assert.ok(report.byteLength > 0);
  assert.equal(engine.MAX_FILES, 200);
  assert.equal(engine.MAX_FILE_BYTES, 512 * 1024);
  assert.equal(engine.MAX_PROJECT_BYTES, 1500 * 1024);
});