import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const profileUrl = new URL("../src/ai/neuron-profile.json", import.meta.url);

test("profile totals more than 264000 logical units", async () => {
  const profile = JSON.parse(await readFile(profileUrl, "utf8"));
  const computedTotal = profile.layerSizes.reduce((sum, size) => sum + size, 0);

  assert.ok(profile.layerSizes.length > 1);
  assert.ok(profile.layerSizes.every((size) => Number.isInteger(size) && size > 0));
  assert.equal(computedTotal, profile.totalLogicalUnits);
  assert.ok(computedTotal > profile.requiredMinimumExclusive);
  assert.equal(computedTotal, 264192);
});

test("profile does not falsely claim trained weights or implemented inference", async () => {
  const profile = JSON.parse(await readFile(profileUrl, "utf8"));
  assert.equal(profile.trainingStatus, "not-trained");
  assert.equal(profile.inferenceStatus, "not-implemented");
  assert.equal(profile.weightsIncluded, false);
});