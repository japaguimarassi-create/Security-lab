const REQUIRED_DIMENSIONS = ["correctness", "tests", "security", "instructionAdherence", "evidence"];

export function evaluateQuality({ checks = [], changedFiles = [], hasEvidence = false } = {}) {
  const byId = new Map(checks.map((check) => [check.id, check]));
  const dimensions = REQUIRED_DIMENSIONS.map((id) => {
    const check = byId.get(id);
    return {
      id,
      passed: Boolean(check?.passed),
      evidence: typeof check?.evidence === "string" ? check.evidence : "No evidence supplied."
    };
  });
  const passed = dimensions.filter((dimension) => dimension.passed).length;
  const missingEvidence = !hasEvidence;
  const hasChanges = Array.isArray(changedFiles) && changedFiles.length > 0;
  const ready = passed === REQUIRED_DIMENSIONS.length && !missingEvidence;

  return {
    status: ready ? "ready_for_human_review" : "needs_work",
    score: Math.round((passed / REQUIRED_DIMENSIONS.length) * 100),
    passedDimensions: passed,
    totalDimensions: REQUIRED_DIMENSIONS.length,
    missingEvidence,
    hasChanges,
    dimensions
  };
}