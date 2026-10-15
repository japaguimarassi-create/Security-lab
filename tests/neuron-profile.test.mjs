import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const profileUrl = new URL("../src/ai/neuron-profile.json", import.meta.url);

test("profile reports exactly 264192 trainable parameters", async () => {
  const profile = JSON.parse(await readFile(profileUrl, "utf8"));
  assert.equal(profile.totalTrainableParameters, 264192);
  assert.equal(profile.unitType, "trainable_parameter");
  assert.equal(profile.architecture.type, "single-layer LSTM autoregressive language model");
});

test("profile describes local inference and the training limitations accurately", async () => {
  const profile = JSON.parse(await readFile(profileUrl, "utf8"));
  assert.equal(profile.trainingStatus, "trained-from-random-initialization-during-apk-build");
  assert.equal(profile.inferenceStatus, "local-javascript-lstm");
  assert.equal(profile.weightsIncludedInApk, true);
  assert.equal(profile.pretrainedWeightsUsed, false);
  assert.ok(profile.notes.some(note => note.includes("not a count of biological")));
});
