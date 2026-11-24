from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Any

from .games import GameAdapter
from .network import SparsePolicyNetwork


@dataclass
class MatchResult:
    game: str
    winner: int | None
    plies: int
    termination: str
    moves: list[str]
    repetitions: int = 0
    error_flags: list[str] | None = None


class RandomOpponent:
    def __init__(self, seed: int = 7):
        self.rng = Random(seed)

    def choose(self, game: GameAdapter, state: Any, actions: list[Any]) -> Any:
        return self.rng.choice(actions)


class GreedyOpponent:
    def choose(self, game: GameAdapter, state: Any, actions: list[Any]) -> Any:
        return max(actions, key=lambda action: (game.features(state, action)[0] * 2.0 + game.features(state, action)[2] * 1.5 + game.features(state, action)[12], game.action_label(action)))


class NeuralOpponent:
    def __init__(self, network: SparsePolicyNetwork):
        self.network = network

    def choose_with_diagnostics(self, game: GameAdapter, state: Any, actions: list[Any], history: set[tuple] | None = None) -> tuple[Any, list[str]]:
        features = [game.features(state, action, history) for action in actions]
        scores = [self.network.score(vector) for vector in features]
        chosen_index = max(range(len(actions)), key=lambda i: (scores[i], game.action_label(actions[i])))
        chosen = features[chosen_index]
        flags: list[str] = []
        if chosen[0] <= 0 and any(vector[0] > 0 for vector in features):
            flags.append("missed_capture")
        if chosen[2] <= 0 and any(vector[2] > 0 for vector in features):
            flags.append("missed_promotion")
        if chosen[5] > 0 and any(vector[5] <= 0 for i, vector in enumerate(features) if i != chosen_index):
            flags.append("hung_piece")
        if chosen[6] <= 0 and any(vector[6] > 0 for vector in features):
            flags.append("missed_check")
        if chosen[11] > 0:
            flags.append("repeated_cycle")
        return actions[chosen_index], flags

    def choose(self, game: GameAdapter, state: Any, actions: list[Any], history: set[tuple] | None = None) -> Any:
        return self.choose_with_diagnostics(game, state, actions, history)[0]


def play_match(game: GameAdapter, network: SparsePolicyNetwork, opponent: Any, neural_side: int = 1, max_plies: int = 120) -> MatchResult:
    state = game.initial_state()
    moves: list[str] = []
    position_counts = {game.state_key(state): 1}
    repetitions = 0
    error_flags: list[str] = []
    termination = "ply_limit"
    for _ in range(max_plies):
        if game.terminal(state):
            termination = "terminal_position"
            break
        actions = game.legal_actions(state)
        if not actions:
            termination = "terminal_position"
            break
        if state.turn == neural_side:
            action, flags = NeuralOpponent(network).choose_with_diagnostics(game, state, actions, set(position_counts))
            error_flags.extend(flags)
        else:
            action = opponent.choose(game, state, actions)
        moves.append(game.action_label(action))
        state = game.apply(state, action)
        key = game.state_key(state)
        position_counts[key] = position_counts.get(key, 0) + 1
        if position_counts[key] > 1:
            repetitions += 1
        if position_counts[key] >= 3:
            termination = "repetition_draw"
            break
    winner = game.winner(state) if termination == "terminal_position" else None
    return MatchResult(game.game_id, winner, len(moves), termination, moves, repetitions, sorted(set(error_flags)))
