import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const repoRoot = new URL("..", import.meta.url);
const terminalUrl = new URL("../src/workspace/terminal.js", import.meta.url);
const engineSource = await readFile(new URL("../src/workspace/workspace-engine.js", import.meta.url), "utf8");
const terminalSource = await readFile(terminalUrl, "utf8");

class FakeElement {
  constructor(id = "") {
    this.id = id;
    this.children = [];
    this.listeners = {};
    this.attributes = {};
    this.hidden = id === "terminal-panel";
    this.value = "";
    this.textContent = "";
    this.className = "";
    this.scrollTop = 0;
    this.scrollHeight = 0;
    this.parentNode = null;
  }

  addEventListener(name, handler) {
    this.listeners[name] = handler;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  append(child) {
    child.parentNode = this;
    this.children.push(child);
    this.scrollHeight = this.children.length;
  }

  replaceChildren(...children) {
    this.children = [];
    for (const child of children) this.append(child);
  }

  get firstElementChild() {
    return this.children[0] || null;
  }

  remove() {
    if (!this.parentNode) return;
    this.parentNode.children = this.parentNode.children.filter(child => child !== this);
  }

  click() {
    this.clicked = true;
    const handler = this.listeners.click;
    if (handler) handler({ target: this });
  }

  focus() {
    this.focused = true;
  }
}

function makeRuntime() {
  const storage = new Map();
  const elements = new Map();
  const getElement = id => {
    if (!elements.has(id)) elements.set(id, new FakeElement(id));
    return elements.get(id);
  };
  const fakeDocument = {
    getElementById: getElement,
    createElement: tag => new FakeElement(tag),
    addEventListener(name, handler) {
      getElement("document").listeners[name] = handler;
    }
  };
  const engineWindow = {};
  const engineContext = {
    window: engineWindow,
    TextEncoder,
    TextDecoder,
    Uint8Array,
    Uint32Array,
    DataView
  };
  vm.createContext(engineContext);
  vm.runInContext(engineSource, engineContext);
  const engine = engineWindow.KodexWorkspaceEngine;
  const files = new Map(Object.entries(engine.createStarterProject()));
  const directories = new Set();

  function safePath(path) {
    return engine.normalizeProjectPath(path);
  }

  function ensureParents(path) {
    const parts = path.split("/");
    for (let i = 1; i < parts.length; i += 1) directories.add(parts.slice(0, i).join("/"));
  }

  function list(path = "") {
    const prefix = path ? safePath(path) + "/" : "";
    const nodes = new Map();
    for (const directory of directories) {
      if (!directory.startsWith(prefix)) continue;
      const name = directory.slice(prefix.length).split("/")[0];
      if (name) nodes.set(name, { name, type: "directory" });
    }
    for (const [filePath, content] of files) {
      if (!filePath.startsWith(prefix)) continue;
      const rest = filePath.slice(prefix.length);
      const parts = rest.split("/");
      if (parts.length > 1) {
        nodes.set(parts[0], { name: parts[0], type: "directory" });
      } else {
        nodes.set(parts[0], { name: parts[0], path: filePath, type: "file", bytes: new TextEncoder().encode(content).length });
      }
    }
    return Array.from(nodes.values()).sort((a, b) => a.name.localeCompare(b.name));
  }

  const api = {
    getFiles: () => Array.from(files, ([path, content]) => ({ path, content })),
    getDirectories: () => Array.from(directories),
    list,
    read(path) {
      const safe = safePath(path);
      if (!files.has(safe)) throw new Error("Arquivo não encontrado: " + safe);
      return files.get(safe);
    },
    write(path, content) {
      const safe = safePath(path);
      const created = !files.has(safe);
      files.set(safe, content);
      ensureParents(safe);
      return { path: safe, bytes: new TextEncoder().encode(content).length, created };
    },
    append(path, content) {
      const safe = safePath(path);
      return this.write(safe, (files.get(safe) || "") + content);
    },
    touch(path) {
      const safe = safePath(path);
      if (files.has(safe)) return { path: safe, bytes: new TextEncoder().encode(files.get(safe)).length, created: false };
      return this.write(safe, "");
    },
    mkdir(path) {
      const safe = safePath(path);
      directories.add(safe);
      ensureParents(safe);
      return safe;
    },
    rmdir(path) {
      const safe = safePath(path);
      if (Array.from(files.keys()).some(file => file.startsWith(safe + "/")) || Array.from(directories).some(dir => dir.startsWith(safe + "/"))) {
        throw new Error("O diretório não está vazio.");
      }
      directories.delete(safe);
      return safe;
    },
    remove(path) {
      const safe = safePath(path);
      if (!files.has(safe)) throw new Error("Arquivo não encontrado: " + safe);
      files.delete(safe);
      return safe;
    },
    rename(from, to) {
      const oldPath = safePath(from);
      const newPath = safePath(to);
      if (!files.has(oldPath)) throw new Error("Arquivo não encontrado: " + oldPath);
      if (files.has(newPath)) throw new Error("Já existe um arquivo com esse caminho.");
      const content = files.get(oldPath);
      files.delete(oldPath);
      files.set(newPath, content);
      ensureParents(newPath);
      return { from: oldPath, to: newPath };
    },
    check: () => engine.validateProject(Object.fromEntries(files)),
    previewHtml: () => engine.buildPreviewHtml(Object.fromEntries(files)),
    exportZip: () => engine.buildProjectZip(Object.fromEntries(files))
  };

  const localStorage = {
    getItem(key) { return storage.has(key) ? storage.get(key) : null; },
    setItem(key, value) { storage.set(key, String(value)); },
    removeItem(key) { storage.delete(key); }
  };
  const window = {
    KodexWorkspaceAPI: api,
    KodexWorkspaceEngine: engine,
    confirm: () => true
  };
  const context = {
    window,
    document: fakeDocument,
    localStorage,
    navigator: { hardwareConcurrency: 2 },
    TextEncoder,
    TextDecoder,
    Date,
    JSON,
    Map,
    Set,
    Array,
    String,
    Math,
    RegExp,
    Error,
    Uint8Array
  };
  vm.createContext(context);
  vm.runInContext(terminalSource, context);
  return { elements, files, api, window, engine };
}

async function command(runtime, line) {
  const input = runtime.elements.get("terminal-input");
  const form = runtime.elements.get("terminal-form");
  input.value = line;
  await form.listeners.submit({ preventDefault() {} });
}

test("terminal creates, writes, reads and searches project files", async () => {
  const runtime = makeRuntime();
  await command(runtime, "touch src/main.js");
  await command(runtime, 'write src/main.js "const answer = 42;"');
  await command(runtime, "cat src/main.js");
  await command(runtime, 'grep answer src/main.js');
  assert.match(runtime.files.get("src/main.js"), /const answer = 42/);
  const output = runtime.elements.get("terminal-output").children.map(child => child.textContent).join("\n");
  assert.match(output, /Criado src\/main\.js/);
  assert.match(output, /src\/main\.js:1: const answer = 42/);
});

test("terminal stores a million-trial plan without claiming training has started", async () => {
  const runtime = makeRuntime();
  await command(runtime, "ai queue 1000000");
  const plan = JSON.parse(runtime.api.read("training/sweep-request.json"));
  assert.equal(plan.logicalTrials, 1000000);
  assert.equal(plan.status, "planned-not-executed");
  const output = runtime.elements.get("terminal-output").children.map(child => child.textContent).join("\n");
  assert.match(output, /Nenhum treinamento foi iniciado/);
});

test("terminal prevents escaping the workspace root", async () => {
  const runtime = makeRuntime();
  await command(runtime, "cat ../../secrets.txt");
  const output = runtime.elements.get("terminal-output").children.map(child => child.textContent).join("\n");
  assert.match(output, /não pode sair da raiz/);
});

test("terminal offers only the documented file workspace commands", async () => {
  const runtime = makeRuntime();
  await command(runtime, "help");
  const output = runtime.elements.get("terminal-output").children.map(child => child.textContent).join("\n");
  assert.match(output, /ls \[pasta\]/);
  assert.match(output, /Não é Bash/);
  assert.doesNotMatch(output, /executar qualquer comando/);
});

test("terminal command history is persisted and supports cleanup confirmation", async () => {
  const runtime = makeRuntime();
  await command(runtime, "touch remove-me.txt");
  await command(runtime, "rm remove-me.txt");
  await command(runtime, "history");
  assert.equal(runtime.files.has("remove-me.txt"), false);
  const output = runtime.elements.get("terminal-output").children.map(child => child.textContent).join("\n");
  assert.match(output, /Removido: remove-me\.txt/);
  assert.match(output, /touch remove-me\.txt/);
});
