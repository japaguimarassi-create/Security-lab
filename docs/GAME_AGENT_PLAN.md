# Game-agent implementation plan

1. Establish the isolated \`game-agent/visual-rl-prototype\` branch and add the agent as a separate \`klod.game_agent\` package.
2. Preserve the requested 4,096 × 2,048 target as metadata, while executing a compact sparse core so the first experiment is runnable and measurable.
3. Initialize four distinct, hand-configured expert heads behind a sparse feature router; log every targeted parameter change.
4. Validate chess and checkers legal actions, then run one match in each game against distinct baseline opponents.
5. Diagnose simple error classes and change only their mapped output weights.
6. Run parallel reinforcement episodes against multiple opponent styles, aggregate policy-gradient updates, and report episodes, rewards and weight deltas.
7. Use held-out match suites before claiming progress. Add visual frame perception and real-game control only after the symbolic agent has a reliable baseline.

## Acceptance criteria

- The chess starting position exposes 20 legal moves.
- The checkers starting position exposes legal opening moves and mandatory captures are enforced.
- Illegal moves are rejected by each adapter.
- Error feedback changes only the named parameter.
- A smoke match executes in each game.
- Parallel reinforcement runs both games against random and greedy opponents and changes the policy parameters.
- Documentation clearly distinguishes the 17B-weight target from the compact executable prototype.
