# Engineering research: Codex and GitHub Copilot

Research snapshot: 15 October 2026. The linked official sources are primary references; specific plans, interfaces, and availability can change.

## Findings from OpenAI Codex

1. **Task-based software engineering, not just completion.** The Codex cloud product can take feature work, bug fixes, codebase questions, and pull-request tasks. The 2025 launch description says tasks ran independently in cloud containers preloaded with a repository. The launch post explicitly marks itself as outdated, so use current documentation for current availability and behavior.
   - https://openai.com/pt-BR/index/introducing-codex/
   - https://help.openai.com/pt-br/articles/20001545-using-codex-cloud

2. **A work environment is part of the product.** Cloud tasks use a configured repository and environment with tools and dependencies; each task has its own working files. This suggests Kodex should model a task workspace separately from the user's main branch and keep diffs inspectable.
   - https://help.openai.com/en/articles/20001545-using-codex-cloud

3. **Iteration and evidence matter.** OpenAI describes Codex's software-engineering training as working on real tasks and iterating through tests; the product provides files, terminal logs, and diffs for review. Kodex should expose the steps and validation evidence rather than only returning an answer.
   - https://openai.com/index/o3-o4-mini-codex-system-card-addendum/
   - https://openai.com/index/introducing-upgrades-to-codex/

4. **Sandboxing and approvals are separate controls.** The sandbox defines which files and network resources an agent can access; an approval policy decides when it must stop and ask permission. Kodex must not use a single vague "safe mode" flag as a substitute for enforceable permissions.
   - https://developers.openai.com/pt-BR/docs/sandboxing
   - https://openai.com/pt-BR/index/running-codex-safely/

5. **Tool use and orchestration are core capabilities.** OpenAI's agent documentation distinguishes a managed agent runtime from an SDK controlled by the application, and describes tools, multi-step execution, handoffs, state, guardrails, and observability. Kodex's runtime therefore uses explicit model and tool contracts so it can evolve without binding the UI to a single inference provider.
   - https://developers.openai.com/api/docs/guides/agents
   - https://developers.openai.com/api/docs/guides/agents/sdk
   - https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server

## Findings from GitHub Copilot

1. **Repository-aware context improves software answers.** GitHub documents semantic indexing for repository-aware responses and code search. The index can find relevant code by meaning rather than requiring exact search terms. Kodex should build a local/permissioned index with file paths and snippets, then include retrieved evidence in responses. This repository does not yet implement semantic embeddings.
   - https://docs.github.com/en/copilot/concepts/context/repository-indexing
   - https://docs.github.com/en/copilot/concepts/context

2. **Agent mode works across files and tools.** Copilot agent mode can take a higher-level task, decide which files to edit, run commands, inspect failures, and iterate; users can review edits and approve terminal commands according to configuration. Kodex's long-term work loop should be plan → inspect → propose patch → test → evaluate → ask for approval where required.
   - https://docs.github.com/en/copilot/how-tos/copilot-in-your-ide/use-copilot-agents/use-agent-mode
   - https://docs.github.com/en/copilot/concepts/agents/about-agent-capabilities

3. **Code review is a separate workflow.** Copilot code review analyzes changes, uses project context, and can suggest fixes; GitHub warns that reviews do not identify every issue and should be validated. Kodex should distinguish review findings from proven defects, rank confidence, show evidence and offer patch suggestions.
   - https://docs.github.com/en/copilot/concepts/agents/code-review

4. **Custom instructions are a first-class repository feature.** GitHub documents repository-wide instructions, path-specific instructions, and agent instructions. Kodex has a dedicated project directives file and should later support scoped workspace instructions without merging untrusted repository content with high-authority runtime policy.
   - https://docs.github.com/en/copilot/how-tos/copilot-in-your-ide/customize-copilot/configure-custom-instructions/add-repository-instructions-in-your-ide
   - https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/add-custom-instructions/add-repository-instructions

5. **Extensible tools matter.** GitHub's context documentation covers Model Context Protocol (MCP) integration. Kodex should eventually use a permissioned tool registry rather than letting model text invoke arbitrary integrations.
   - https://docs.github.com/en/copilot/concepts/context


6. **Inline completions and multi-file task agents are different capabilities.** Copilot's inline suggestions provide ghost text while typing and can suggest next edits; agent mode handles broader tasks by inspecting and editing multiple files and invoking tools. Kodex should keep low-latency completion as a separate interface from the slower plan/implement/verify agent loop.
   - https://docs.github.com/en/copilot/concepts/completions/code-suggestions
   - https://docs.github.com/en/copilot/responsible-use/inline-suggestions

7. **Prompt quality depends on relevant context and task structure.** GitHub's guidance recommends clear goals, concrete constraints, explicit relevant code, examples, smaller subtasks, and iterative refinement. Kodex should construct structured task briefs and include only code context relevant to the task, rather than sending the entire repository on every request.
   - https://docs.github.com/en/copilot/concepts/prompting/prompt-engineering

8. **Code provenance and license checks deserve a dedicated feature.** GitHub documents code-reference indications when Copilot Chat outputs code matching public repositories, while noting that matching and indexing have limitations. Kodex should eventually provide provenance and license review where feasible rather than claiming every generated fragment is original or fully cleared.
   - https://docs.github.com/en/copilot/concepts/completions/code-referencing

## Product implications for Kodex

- **Workbench, not chat-only:** editor, explorer, task queue, run/test status, diff review, and explanation/review actions should remain visible alongside conversation.
- **Context pipeline:** collect only permitted files, rank relevant snippets, preserve file/line provenance, and surface retrieved evidence.
- **Bounded agent loop:** model output is data. The runtime validates tool names and arguments, limits steps, validates outputs, and emits a trace.
- **Human-centered control:** separate read/write/execute/network permissions; ask before consequential actions; allow reviewing changes before applying them.
- **Verification:** run tests and static checks where tools are actually available; never claim tests passed if they did not run.
- **Model reality:** Codex and Copilot depend on trained production-grade models plus orchestration and infrastructure. A UI, prompt, neuron count, or heuristic alone cannot reproduce that capability.
- **Quality gates:** score task completion by tests, correctness evidence, safety, instruction adherence, and reviewability. Avoid optimizing for a single self-reported confidence score.

## Scope note

This is a synthesis of public documentation, not reverse engineering of proprietary internals. Kodex should implement its own architecture and avoid implying affiliation with OpenAI or GitHub.