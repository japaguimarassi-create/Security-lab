import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const source = await readFile(new URL("../app.js", import.meta.url), "utf8");
const start = source.indexOf("function normalizeForMatching(");
const end = source.indexOf("\nfunction appendMessage(thread, message)", start);
assert.notEqual(start, -1, "chat routing helpers should exist");
assert.notEqual(end, -1, "chat routing helper boundary should exist");

function createHarness(modelReply = "Tudo bem. Não vou transformar isso em uma tarefa.") {
  const sandbox = {
    window: {
      KodexMobileMLM: {
        ready: true,
        generate: () => modelReply
      }
    },
    makeBuildBrief(prompt) {
      return {
        kind: "build",
        title: "Brief",
        intro: "Brief local de teste.",
        sections: [{ title: "Pedido", items: [prompt] }],
        checklist: []
      };
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(source.slice(start, end), sandbox);
  return (prompt, mode = "chat") => {
    sandbox.prompt = prompt;
    sandbox.mode = mode;
    return vm.runInContext("makeResponse(prompt, mode, [])", sandbox);
  };
}

test("an unknown one-word message asks for context and never creates a build task", () => {
  const respond = createHarness();
  const response = respond("dinossauro");
  assert.equal(response.kind, "chat");
  assert.match(response.text, /dinossauro/i);
  assert.match(response.text, /significado|exemplo|conversar/i);
  assert.equal(response.modelGenerated, false);
});

test("a single word stays conversational even if the build mode was selected", () => {
  const respond = createHarness();
  const response = respond("C++", "build");
  assert.equal(response.kind, "chat");
  assert.equal(response.modelGenerated, false);
});

test("common programming terms get a relevant local explanation", () => {
  const respond = createHarness();
  const response = respond("me explique uma variável");
  assert.equal(response.kind, "chat");
  assert.match(response.text, /nome associado a um valor/i);
  assert.equal(response.modelGenerated, false);
});

test("off-topic neural output is discarded instead of presented as an answer", () => {
  const respond = createHarness("Tudo bem. Não vou transformar isso em uma tarefa.");
  const response = respond("Como compilar o APK no Android?");
  assert.equal(response.kind, "chat");
  assert.equal(response.modelGenerated, false);
  assert.doesNotMatch(response.text, /transformar isso em uma tarefa/i);
});

test("build requests keep a structured brief when the model response is irrelevant", () => {
  const respond = createHarness("Tudo bem. Não vou transformar isso em uma tarefa.");
  const response = respond("Crie um app para Android", "build");
  assert.equal(response.kind, "build");
  assert.doesNotMatch(JSON.stringify(response.sections), /transformar isso em uma tarefa/i);
});