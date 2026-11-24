from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from random import Random
from typing import Any, Callable

from .games import ChessGame, DraughtsGame, GameAdapter
from .network import FEATURES, SparsePolicyNetwork
from .runner import GreedyOpponent, RandomOpponent


@dataclass
class EpisodeResult:
    game: str
    opponent: str
    reward: float
    plies: int
    gradient: list[list[float]]
    winner: int | None


class ReinforcementTrainer:
    def __init__(self, network: SparsePolicyNetwork, learning_rate: float = 0.015, temperature: float = 1.6, workers: int = 4, seed: int = 19):
        if learning_rate <= 0 or workers < 1:
            raise ValueError("learning_rate and workers must be positive")
        self.network = network
        self.learning_rate = learning_rate
        self.temperature = temperature
        self.workers = workers
        self.seed = seed

    def _episode(self, game: GameAdapter, opponent_name: str, opponent_factory: Callable[[int], Any], side: int, episode_seed: int, max_plies: int, network: SparsePolicyNetwork) -> EpisodeResult:
        opponent = opponent_factory(episode_seed + 101)
        rng = Random(episode_seed)
        state = game.initial_state()
        trace: list[tuple[list[tuple[float, ...]], int]] = []
        seen = {game.state_key(state): 1}
        plies = 0
        repeated = False
        while plies < max_plies and not game.terminal(state):
            actions = game.legal_actions(state)
            if not actions:
                break
            if state.turn == side:
                candidates = [game.features(state, action, set(seen)) for action in actions]
                probabilities = network.probabilities(candidates, self.temperature)
                pick = rng.choices(range(len(actions)), weights=probabilities, k=1)[0]
                trace.append((candidates, pick))
                action = actions[pick]
            else:
                action = opponent.choose(game, state, actions)
            state = game.apply(state, action)
            key = game.state_key(state)
            seen[key] = seen.get(key, 0) + 1
            repeated = seen[key] >= 3
            plies += 1
            if repeated:
                break
        winner = game.winner(state) if game.terminal(state) and not repeated else None
        if winner == side:
            reward = 1.0
        elif winner == -side:
            reward = -1.0
        else:
            material = 0.0
            if game.game_id == "chess":
                values = {"p": 1.0, "n": 3.0, "b": 3.0, "r": 5.0, "q": 9.0, "k": 0.0}
                material = sum((1.0 if piece.isupper() else -1.0) * values[piece.lower()] for piece in state.board if piece)
            else:
                material = sum((1.0 if piece > 0 else -1.0) * (1.8 if abs(piece) == 2 else 1.0) for piece in state.board if piece)
            reward = max(-0.45, min(0.45, material * side / 12.0))
        gradient = [[0.0 for _ in FEATURES] for _ in network.expert_heads]
        for index, (candidates, chosen) in enumerate(trace):
            discount = 0.985 ** (len(trace) - index - 1)
            selected = candidates[chosen]
            shaping = 0.12 * (selected[0] + selected[2] + selected[12] + selected[13] - selected[5])
            effective_reward = max(-1.0, min(1.0, reward * discount + shaping))
            update = network.policy_gradient(candidates, chosen, effective_reward, self.learning_rate, self.temperature)
            gradient = [[old + new for old, new in zip(old_row, new_row)] for old_row, new_row in zip(gradient, update)]
        return EpisodeResult(game.game_id, opponent_name, reward, plies, gradient, winner)

    def run(self, episodes_per_game: int = 4, max_plies: int = 100) -> list[EpisodeResult]:
        if episodes_per_game < 1 or max_plies < 1:
            raise ValueError("episodes_per_game and max_plies must be positive")
        games = (ChessGame(), DraughtsGame())
        opponents = (("random", lambda seed: RandomOpponent(seed)), ("greedy", lambda seed: GreedyOpponent()))
        tasks = []
        snapshot = self.network.clone()
        episode_id = 0
        for game in games:
            for opponent_name, factory in opponents:
                for _ in range(episodes_per_game):
                    side = 1 if episode_id % 2 == 0 else -1
                    tasks.append((game, opponent_name, factory, side, self.seed + episode_id * 13, max_plies, snapshot.clone()))
                    episode_id += 1
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            results = list(pool.map(lambda args: self._episode(*args), tasks))
        if results:
            average = [
                [sum(item.gradient[expert][index] for item in results) / len(results) for index in range(self.network.spec.second_width)]
                for expert in range(self.network.spec.active_experts)
            ]
            self.network.apply_output_gradient(average)
        return results
