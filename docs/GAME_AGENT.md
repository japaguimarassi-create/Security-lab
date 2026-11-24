# KLOD Game Agent — sparse prototype

This branch adds an isolated game-agent experiment under \`src/klod/game_agent/\`. It does not modify the existing KLOD chat runtime.

## What is implemented

- One shared action-scoring network used by both chess and checkers adapters.
- A target profile recording the requested logical topology of 4,096 × 2,048.
- A compact sparse runtime core (16 input features → 32 hidden units → 16 hidden units → four expert output heads). A feature router activates at most two heads per action. The 4,096 × 2,048 dense tensor is **not** allocated: it would require over 17 billion connection weights before biases. The target profile is a capacity goal, not a claim that this prototype contains that many learned parameters.
- Hand-authored starting priors for captures, promotions, center control, piece exposure, king safety, mobility and multi-captures.
- Targeted error feedback that changes only the output parameter associated with the diagnosed mistake.
- Self-contained legal-move engines for chess and American checkers.
- A match runner and parallel REINFORCE-style updates from outcomes against random and greedy opponents.

## Important distinction

Manual priors are not equivalent to hours or weeks of training. They encode explicit heuristics. The reinforcement loop then performs actual parameter updates from simulated match rewards. Performance claims require repeated tournaments against held-out opponents and positions; the smoke experiment in this branch is not evidence of universal game skill.

## Run locally

Python 3.11+; no third-party runtime dependency is required for this prototype.

\`\`\`bash
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python scripts/run_game_agent_experiment.py
\`\`\`

## Current scope and next stage

The adapters consume symbolic legal game states. They do not yet infer a board from raw video, screenshots or arbitrary game frames, and they do not inject input into external games. The next stage is a visual observation adapter: frame sampling, game-specific perception, confidence tracking, state reconstruction, and a safe action interface. Each new game needs an adapter that maps observations to legal candidate actions.

The initial chess implementation covers standard board movement, check legality, castling, en passant, promotion and terminal mate/stalemate detection. The checkers implementation uses mandatory captures, multi-jumps and king promotion for an 8×8 American-checkers ruleset.
