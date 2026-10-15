import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("../src/terminal/terminal.js", import.meta.url), "utf8");
const page = await readFile(new URL("../terminal.html", import.meta.url), "utf8");

test("terminal JavaScript parses and the page loads the workspace engine before the terminal", () => {
  assert.doesNotThrow(() => new Function(source));
  assert.ok(page.indexOf("src/workspace/workspace-engine.js") < page.indexOf("src/terminal/terminal.js"));
});

test("execution uses a sandboxed iframe without same-origin permission", () => {
  assert.match(page, /sandbox="allow-scripts"/);
  assert.doesNotMatch(page, /sandbox="[^"]*allow-same-origin/);
  assert.match(source, /connect-src 'none'/);
  assert.match(source, /form-action 'none'/);
  assert.match(source, /frame-src 'none'/);
});

test("terminal explicitly refuses unrestricted operating-system shell commands", () => {
  assert.match(source, /não executa/);
  assert.match(source, /sistema operacional/);
  assert.match(source, /run js/);
  assert.match(source, /train plan/);
});
