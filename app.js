const sampleFiles = {
  "src/main.js": [
    "import { sum } from './math.js';",
    "",
    "export function startApp() {",
    "  const result = sum(18, 24);",
    "  console.log('Kodex sample:', result);",
    "  return result;",
    "}",
    "",
    "startApp();"
  ].join("\n"),
  "src/math.js": [
    "export function sum(a, b) {",
    "  if (typeof a !== 'number' || typeof b !== 'number') {",
    "    throw new TypeError('sum expects numbers');",
    "  }",
    "  return a + b;",
    "}"
  ].join("\n"),
  "tests/math.test.js": [
    "import test from 'node:test';",
    "import assert from 'node:assert/strict';",
    "import { sum } from '../src/math.js';",
    "",
    "test('sum combines two numbers', () => {",
    "  assert.equal(sum(2, 3), 5);",
    "});"
  ].join("\n"),
  "README.md": [
    "# Kodex sample workspace",
    "",
    "A small JavaScript project used to exercise the workbench.",
    "",
    "- src/main.js: application entry point",
    "- src/math.js: arithmetic helper",
    "- tests/math.test.js: one Node.js test example",
    "",
    "The browser workbench inspects source text locally. It does not run this code."
  ].join("\n")
};

const editor = document.getElementById("source-editor");
const lineNumbers = document.getElementById("line-numbers");
const activeFileName = document.getElementById("active-file-name");
const breadcrumbFile = document.getElementById("breadcrumb-file");
const editorHeading = document.getElementById("editor-heading");
const editorStatusText = document.getElementById("editor-status-text");
const cursorStatus = document.getElementById("cursor-status");
const unsavedDot = document.getElementById("unsaved-dot");
const mobileFileSelect = document.getElementById("mobile-file-select");
const responseContent = document.getElementById("response-content");
const taskList = document.getElementById("task-list");
const queueCount = document.getElementById("queue-count");
const toast = document.getElementById("toast");
const consoleBody = document.getElementById("console-body");
const logCount = document.getElementById("log-count");
const fileState = {};
const taskQueue = [];
let activeFile = "src/main.js";
let activeMode = "ask";
let activeView = "workspace";
let toastHandle = null;

function fileTitle(path) {
  return path.split("/").pop();
}

function startingContent(path) {
  try {
    return localStorage.getItem("kodex-lab:file:" + path) ?? sampleFiles[path];
  } catch {
    return sampleFiles[path];
  }
}

Object.keys(sampleFiles).forEach((path) => {
  fileState[path] = {
    content: startingContent(path),
    savedContent: startingContent(path)
  };
});

function appendLog(level, message) {
  const row = document.createElement("div");
  row.className = "log-row" + (level === "INFO" ? " log-muted" : "");
  const time = document.createElement("span");
  time.className = "log-time";
  time.textContent = level;
  const mark = document.createElement("span");
  mark.className = "log-mark";
  mark.textContent = level === "PASS" ? "✓" : level === "WARN" ? "!" : "›";
  const text = document.createElement("span");
  text.textContent = message;
  row.append(time, mark, text);
  consoleBody.append(row);
  consoleBody.scrollTop = consoleBody.scrollHeight;
  logCount.textContent = String(consoleBody.querySelectorAll(".log-row").length).padStart(2, "0");
}

function showToast(message) {
  toast.textContent = message;
  toast.hidden = false;
  if (toastHandle) clearTimeout(toastHandle);
  toastHandle = setTimeout(() => {
    toast.hidden = true;
  }, 2600);
}

function updateEditorChrome() {
  const state = fileState[activeFile];
  const title = fileTitle(activeFile);
  activeFileName.textContent = title;
  breadcrumbFile.textContent = title;
  editorHeading.textContent = activeFile === "src/main.js"
    ? "Application entry"
    : activeFile === "src/math.js"
      ? "Core utility"
      : activeFile === "tests/math.test.js"
        ? "Test specification"
        : "Project documentation";
  const ext = title.split(".").pop().toLowerCase();
  const language = ext === "md" ? "Markdown" : ext === "ts" || ext === "tsx" ? "TypeScript" : "JavaScript";
  document.querySelector(".editor-status > div:last-child span:nth-child(2)").textContent = language;
  mobileFileSelect.value = activeFile;
  document.querySelectorAll(".file-row").forEach((button) => {
    button.classList.toggle("selected", button.dataset.file === activeFile);
  });
  const dirty = state.content !== state.savedContent;
  unsavedDot.hidden = !dirty;
  editorStatusText.textContent = dirty ? "Unsaved local changes" : "Ready for local inspection";
  updateLineNumbers();
}

function updateLineNumbers() {
  const count = Math.max(1, editor.value.split("\n").length);
  lineNumbers.textContent = Array.from({ length: count }, (_, index) => String(index + 1)).join("\n");
  lineNumbers.scrollTop = editor.scrollTop;
  updateCursorStatus();
}

function updateCursorStatus() {
  const beforeCursor = editor.value.slice(0, editor.selectionStart);
  const lines = beforeCursor.split("\n");
  cursorStatus.textContent = "Ln " + lines.length + ", Col " + (lines[lines.length - 1].length + 1);
}

function openFile(path) {
  if (!Object.prototype.hasOwnProperty.call(fileState, path)) return;
  fileState[activeFile].content = editor.value;
  activeFile = path;
  editor.value = fileState[path].content;
  updateEditorChrome();
  editor.focus();
  appendLog("INFO", "Opened " + path + " in local workspace.");
}

function renderResponse(flag, paragraphs) {
  responseContent.replaceChildren();
  const flagRow = document.createElement("div");
  flagRow.className = "response-flag";
  const label = document.createElement("span");
  label.textContent = flag || "LOCAL MODE";
  const state = document.createElement("span");
  state.textContent = "NO MODEL";
  flagRow.append(label, state);
  responseContent.append(flagRow);
  paragraphs.forEach((text) => {
    const paragraph = document.createElement("p");
    paragraph.textContent = text;
    responseContent.append(paragraph);
  });
}

function scanCode(code) {
  const checks = [
    {
      id: "eval",
      expression: /\beval\s*\(/,
      severity: "high",
      title: "Dynamic evaluation",
      detail: "eval() executes text as code and can turn untrusted input into executable logic."
    },
    {
      id: "function-constructor",
      expression: /new\s+Function\s*\(/,
      severity: "high",
      title: "Function constructor",
      detail: "The Function constructor creates code from strings and complicates security review."
    },
    {
      id: "embedded-secret",
      expression: /\b(?:api[_-]?key|password|secret|access[_-]?token)\s*[:=]\s*['"][^'"]{8,}['"]/i,
      severity: "high",
      title: "Possible hard-coded secret",
      detail: "A string assignment resembles a credential. Confirm it is not a real secret and rotate it if exposed."
    },
    {
      id: "innerhtml",
      expression: /\.innerHTML\s*=/,
      severity: "medium",
      title: "HTML injection surface",
      detail: "Check whether assigned HTML can contain untrusted input; textContent is safer for plain text."
    },
    {
      id: "fetch",
      expression: /\bfetch\s*\(/,
      severity: "low",
      title: "Network request",
      detail: "Review the destination, data sent, error handling, and permission expectations."
    }
  ];
  return checks.filter((check) => check.expression.test(code));
}

function actionExplain() {
  const code = editor.value;
  const lines = code.split("\n");
  const imports = (code.match(/\bimport\s+(?:[^;]+\s+from\s+)?['"][^'"]+['"]/g) || []).length;
  const exports = (code.match(/\bexport\s+/g) || []).length;
  const functions = (code.match(/\bfunction\s+[A-Za-z_$][\w$]*\s*\(|\b(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>/g) || []).length;
  const comments = (code.match(/(^|\s)\/\//g) || []).length;
  renderResponse("STRUCTURAL PASS", [
    "File: " + activeFile,
    "This local inspection counted " + lines.length + " lines, " + imports + " import statement(s), " + exports + " export keyword(s), and about " + functions + " function declaration(s).",
    "These counts are regex-based approximations. They do not build an AST or prove what the program does.",
    comments ? "Line-comment markers detected: " + comments + "." : "No obvious line-comment markers were detected."
  ]);
  appendLog("PASS", "Structural inspection completed for " + activeFile + " (no code execution).");
}

function actionReview() {
  const findings = scanCode(editor.value);
  responseContent.replaceChildren();
  const flag = document.createElement("div");
  flag.className = "response-flag";
  const left = document.createElement("span");
  left.textContent = "PATTERN SCAN";
  const right = document.createElement("span");
  right.textContent = findings.length ? findings.length + " FINDING(S)" : "NO MATCHES";
  flag.append(left, right);
  responseContent.append(flag);
  const summary = document.createElement("p");
  summary.textContent = findings.length
    ? "Potential review points found in " + activeFile + ". Each match needs contextual validation."
    : "No known risk patterns matched in " + activeFile + ". This does not prove the file is secure.";
  responseContent.append(summary);
  findings.forEach((finding) => {
    const card = document.createElement("div");
    card.className = "finding " + (finding.severity === "high" ? "high" : finding.severity === "low" ? "low" : "");
    const title = document.createElement("strong");
    title.textContent = finding.severity.toUpperCase() + " · " + finding.title;
    const detail = document.createElement("small");
    detail.textContent = finding.detail;
    card.append(title, detail);
    responseContent.append(card);
  });
  const note = document.createElement("p");
  note.className = "response-hint";
  note.textContent = "Static regex scan only: false positives and missed issues are expected. No files, network requests, or commands were executed.";
  responseContent.append(note);
  appendLog(findings.length ? "WARN" : "PASS", "Pattern scan found " + findings.length + " potential issue(s) in " + activeFile + ".");
}

function actionTests() {
  const code = editor.value;
  const hasExport = /\bexport\s+/.test(code);
  const hasThrow = /\bthrow\s+/.test(code);
  const hasBranches = /\bif\s*\(|\bswitch\s*\(/.test(code);
  const hasAsync = /\basync\b|\bawait\b|\bPromise\b/.test(code);
  const cases = [
    hasExport ? "Test the public exported behavior through its public interface." : "Identify the intended public interface and test it directly.",
    hasBranches ? "Cover each conditional branch, including boundary and invalid inputs." : "Add boundary, invalid-input, and typical-input cases appropriate to the function.",
    hasThrow ? "Assert the expected error type and message for invalid inputs." : "Decide which invalid inputs should be rejected and assert the contract.",
    hasAsync ? "Test success, rejection, timeout behavior, and cleanup for asynchronous paths." : "Add regression tests for known defects and run the suite in CI."
  ];
  renderResponse("TEST DESIGN", [
    "Draft checklist for " + activeFile + ".",
    ...cases,
    "This is a proposed checklist, not an executed test run. No test files were changed."
  ]);
  appendLog("INFO", "Generated a test checklist for " + activeFile + "; tests were not executed.");
}

function runAction(action) {
  if (action === "explain") actionExplain();
  else if (action === "review") actionReview();
  else if (action === "tests") actionTests();
}

function performLocalChecks() {
  fileState[activeFile].content = editor.value;
  const findings = scanCode(editor.value);
  const trailingWhitespace = editor.value.split("\n").filter((line) => /\s+$/.test(line)).length;
  const empty = editor.value.trim().length === 0;
  const messages = [];
  messages.push(empty ? "The editor buffer is empty." : "Buffer has " + editor.value.split("\n").length + " line(s).");
  messages.push("Risk-pattern matches: " + findings.length + ".");
  messages.push("Lines with trailing whitespace: " + trailingWhitespace + ".");
  messages.push("Static check finished. No JavaScript was executed and no Node.js tests were run.");
  renderResponse("LOCAL CHECKS", messages);
  appendLog(findings.length ? "WARN" : "PASS", "Local checks completed: " + findings.length + " risk-pattern match(es), " + trailingWhitespace + " trailing-whitespace line(s).");
  editorStatusText.textContent = "Local static checks completed";
  showToast("Local inspection finished; no code was executed.");
}

function saveLocal() {
  fileState[activeFile].content = editor.value;
  try {
    localStorage.setItem("kodex-lab:file:" + activeFile, editor.value);
    fileState[activeFile].savedContent = editor.value;
    updateEditorChrome();
    appendLog("PASS", "Saved " + activeFile + " in this browser's local storage.");
    showToast("Saved in this browser only.");
  } catch {
    appendLog("WARN", "Browser storage is unavailable; the edit remains in the current page session.");
    showToast("Browser storage unavailable; edit remains in this session.");
  }
}

function formatCurrentBuffer() {
  const prior = editor.value;
  const formatted = prior.split("\n").map((line) => line.replace(/[ \t]+$/, "")).join("\n").replace(/\n*$/, "\n");
  editor.value = formatted;
  fileState[activeFile].content = formatted;
  updateEditorChrome();
  editorStatusText.textContent = "Whitespace normalization only";
  appendLog("INFO", "Removed trailing whitespace and ensured one final newline; no language formatter is configured.");
  showToast("Applied basic whitespace cleanup, not a language-aware format.");
}

function renderTasks() {
  taskList.replaceChildren();
  queueCount.textContent = String(taskQueue.length);
  if (taskQueue.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-queue";
    empty.textContent = "No tasks in this session.";
    taskList.append(empty);
    return;
  }
  taskQueue.slice().reverse().forEach((task) => {
    const card = document.createElement("div");
    card.className = "queue-task";
    card.textContent = task.text;
    const status = document.createElement("small");
    status.textContent = task.status;
    card.append(status);
    taskList.append(card);
  });
}

function addTask(event) {
  event.preventDefault();
  const input = document.getElementById("task-input");
  const task = input.value.trim();
  if (!task) return;
  taskQueue.push({ text: task, status: "QUEUED · MODEL REQUIRED" });
  renderTasks();
  input.value = "";
  renderResponse("TASK QUEUED", [
    "Added task to this browser session: " + task,
    "The task has not been run. This branch has no trained model or connected inference endpoint.",
    "When the runtime is implemented, the task should proceed through context gathering, planning, approved tools, tests, and a reviewable diff."
  ]);
  appendLog("INFO", "Queued a session-only task; no model call was made.");
  showToast("Task added to the local queue. It has not been executed.");
}

function setMode(mode) {
  activeMode = mode;
  document.querySelectorAll(".mode-option").forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === mode);
  });
  const label = mode === "build" ? "BUILD" : mode === "review" ? "REVIEW" : "ASK";
  document.querySelector(".task-composer label").textContent = "NEW " + label + " TASK";
  if (mode === "build") {
    renderResponse("BUILD MODE", [
      "Describe the intended change and expected behavior in the task box.",
      "Kodex currently queues the task locally; it does not write files or run commands."
    ]);
  } else if (mode === "review") {
    renderResponse("REVIEW MODE", [
      "Use Inspect for risks for a pattern-based review of the open file.",
      "Findings are candidates for review, not proof of a vulnerability or proof of safety."
    ]);
  } else {
    renderResponse("ASK MODE", [
      "Ask about the current file or use Explain this file.",
      "This first milestone provides deterministic local tools, not generative model inference."
    ]);
  }
}

function setView(view) {
  activeView = view;
  document.querySelectorAll(".rail-item[data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  const labelMap = {
    workspace: "WORKSPACE",
    build: "BUILD",
    review: "REVIEW",
    knowledge: "KNOWLEDGE INDEX",
    tests: "TEST LAB"
  };
  document.getElementById("view-label").textContent = labelMap[view] || "WORKSPACE";
  if (view === "workspace") {
    setMode("ask");
    appendLog("INFO", "Workspace view selected.");
  } else if (view === "build") {
    setMode("build");
  } else if (view === "review") {
    setMode("review");
    actionReview();
  } else if (view === "knowledge") {
    renderResponse("INDEX NOT CONNECTED", [
      "Repository-aware semantic indexing is not implemented in this milestone.",
      "The next implementation should index permitted files, rank relevant snippets, retain file and line provenance, and protect against instructions embedded in untrusted source files."
    ]);
    appendLog("INFO", "Knowledge index selected; no repository index is connected.");
  } else if (view === "tests") {
    actionTests();
  }
}

document.querySelectorAll(".file-row").forEach((button) => {
  button.addEventListener("click", () => openFile(button.dataset.file));
});
mobileFileSelect.addEventListener("change", () => openFile(mobileFileSelect.value));
editor.addEventListener("input", () => {
  fileState[activeFile].content = editor.value;
  updateEditorChrome();
});
editor.addEventListener("click", updateCursorStatus);
editor.addEventListener("keyup", updateCursorStatus);
editor.addEventListener("scroll", () => {
  lineNumbers.scrollTop = editor.scrollTop;
});
document.getElementById("save-local").addEventListener("click", saveLocal);
document.getElementById("format-code").addEventListener("click", formatCurrentBuffer);
document.getElementById("run-checks").addEventListener("click", performLocalChecks);
document.getElementById("task-form").addEventListener("submit", addTask);
document.querySelectorAll("[data-action]").forEach((button) => {
  button.addEventListener("click", () => runAction(button.dataset.action));
});
document.querySelectorAll("[data-mode]").forEach((button) => {
  button.addEventListener("click", () => setMode(button.dataset.mode));
});
document.querySelectorAll(".rail-item[data-view]").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});
document.getElementById("toggle-project").addEventListener("click", () => {
  document.body.classList.toggle("project-collapsed");
});
document.getElementById("assistant-menu").addEventListener("click", () => {
  renderResponse("RUNTIME INFORMATION", [
    "Kodex 0.1.0 is a front-end workbench with deterministic local inspections.",
    "No API key or remote model is configured. The neuron profile is untrained and is not used for inference.",
    "No code execution, file-system access, or Git writes are available from the web interface."
  ]);
});
document.getElementById("close-tab").addEventListener("click", () => {
  if (activeFile !== "src/main.js") {
    openFile("src/main.js");
    return;
  }
  showToast("The entry tab stays open in this prototype.");
});
document.getElementById("clear-log").addEventListener("click", () => {
  consoleBody.replaceChildren();
  logCount.textContent = "00";
});
window.addEventListener("beforeunload", () => {
  fileState[activeFile].content = editor.value;
});

editor.value = fileState[activeFile].content;
updateEditorChrome();
renderTasks();
