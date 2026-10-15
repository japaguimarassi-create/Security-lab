export const HEURISTIC_MODEL_NOTICE =
  "Kodex's heuristic fallback is deterministic demonstration logic, not a trained language model.";

export function createHeuristicModel() {
  return {
    async complete({ messages }) {
      const latestUserMessage = [...messages].reverse().find((message) => message.role === "user");
      const task = latestUserMessage?.content ?? "";
      return {
        type: "final",
        output: [
          "Kodex local scaffold received the task:",
          task,
          "",
          "No trained model is connected. This response does not claim to solve or execute the task.",
          "Next step: connect a trained local model or an authorized server-side inference adapter, then validate outputs with tools and tests."
        ].join("\n")
      };
    }
  };
}