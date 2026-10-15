import test from "node:test";
import assert from "node:assert/strict";
import { runAgentTask, AgentLoopError } from "../src/ai/agent-loop.mjs";

test("agent executes only registered tools and returns a final answer", async () => {
  const calls = [];
  const model = {
    async complete({ messages }) {
      if (!messages.some((message) => message.role === "tool")) {
        return { type: "tool_call", name: "readSnippet", args: { path: "src/example.js" } };
      }
      return { type: "final", output: "Reviewed the supplied snippet." };
    }
  };
  const tools = {
    readSnippet: {
      async execute(args) {
        calls.push(args.path);
        return { ok: true, content: "export const sum = (a, b) => a + b;" };
      }
    }
  };

  const result = await runAgentTask({ task: "Review the sum function", model, tools });

  assert.equal(result.status, "completed");
  assert.equal(result.output, "Reviewed the supplied snippet.");
  assert.deepEqual(calls, ["src/example.js"]);
  assert.ok(result.trace.some((event) => event.type === "tool_finished"));
});

test("agent does not execute approval-gated tools without approval", async () => {
  let executed = false;
  const model = {
    async complete({ messages }) {
      if (!messages.some((message) => message.role === "tool")) {
        return { type: "tool_call", name: "writeFile", args: { path: "src/a.js", content: "x" } };
      }
      return { type: "final", output: "No write was approved." };
    }
  };
  const tools = {
    writeFile: {
      requiresApproval: true,
      async execute() {
        executed = true;
        return { ok: true };
      }
    }
  };

  const result = await runAgentTask({ task: "Write a file", model, tools });

  assert.equal(executed, false);
  assert.equal(result.status, "completed");
  assert.ok(result.trace.some((event) => event.type === "approval_denied"));
});

test("agent refuses empty tasks and invalid step limits", async () => {
  const model = { async complete() { return { type: "final", output: "ok" }; } };
  await assert.rejects(runAgentTask({ task: " ", model }), AgentLoopError);
  await assert.rejects(runAgentTask({ task: "hello", model, maxSteps: 33 }), AgentLoopError);
});

test("agent stops after the configured step budget", async () => {
  const model = { async complete() { return { type: "tool_call", name: "noop", args: {} }; } };
  const result = await runAgentTask({
    task: "Do a bounded task",
    model,
    tools: { noop: { async execute() { return "done"; } } },
    maxSteps: 2
  });
  assert.equal(result.status, "limit_reached");
  assert.equal(result.steps, 2);
});

test("agent reports cancellation before asking the model for work", async () => {
  const controller = new AbortController();
  controller.abort();
  let called = false;
  const model = { async complete() { called = true; return { type: "final", output: "no" }; } };
  const result = await runAgentTask({ task: "Cancelled task", model, signal: controller.signal });
  assert.equal(result.status, "cancelled");
  assert.equal(called, false);
});