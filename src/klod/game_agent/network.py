from __future__ import annotations

from dataclasses import dataclass
from math import exp, tanh
from random import Random
from typing import Sequence

FEATURES = (
    "capture_value",
    "moving_piece_value",
    "promotion_value",
    "center_delta",
    "advancement",
    "exposed_piece",
    "gives_check",
    "castling",
    "protection",
    "opponent_threat",
    "mobility_delta",
    "repetition_penalty",
    "material_gain",
    "multi_capture",
    "king_piece",
    "tempo",
)

INITIAL_PRIORS = {
    "capture_value": 2.20,
    "moving_piece_value": 0.03,
    "promotion_value": 2.80,
    "center_delta": 0.52,
    "advancement": 0.24,
    "exposed_piece": -2.45,
    "gives_check": 0.62,
    "castling": 0.48,
    "protection": 0.38,
    "opponent_threat": -0.42,
    "mobility_delta": 0.30,
    "repetition_penalty": -0.55,
    "material_gain": 1.15,
    "multi_capture": 1.35,
    "king_piece": 0.12,
    "tempo": 0.04,
}

FEEDBACK_RULES = {
    "missed_capture": ("capture_value", 0.12),
    "missed_promotion": ("promotion_value", 0.15),
    "hung_piece": ("exposed_piece", -0.16),
    "missed_check": ("gives_check", 0.06),
    "unsafe_king": ("castling", 0.04),
    "repeated_cycle": ("repetition_penalty", -0.12),
    "missed_multi_capture": ("multi_capture", 0.12),
    "failed_to_progress": ("advancement", 0.08),
}


@dataclass(frozen=True)
class NetworkSpec:
    requested_layers: int = 4096
    requested_width: int = 2048
    active_experts: int = 4
    input_features: int = len(FEATURES)
    hidden_width: int = 32
    second_width: int = 16

    @property
    def requested_dense_parameters(self) -> int:
        return (self.requested_layers - 1) * self.requested_width * self.requested_width

    @property
    def active_parameters(self) -> int:
        return self.input_features * self.hidden_width + self.hidden_width * self.second_width + self.active_experts * self.second_width + self.hidden_width + self.second_width + self.active_experts


@dataclass
class WeightChange:
    error: str
    feature: str
    before: float
    after: float


class SparsePolicyNetwork:
    def __init__(self, spec: NetworkSpec | None = None, seed: int = 41):
        self.spec = spec or NetworkSpec()
        if self.spec.input_features != len(FEATURES):
            raise ValueError("input_features must match the feature contract")
        rng = Random(seed)
        self.w1 = [[0.0 for _ in FEATURES] for _ in range(self.spec.hidden_width)]
        self.b1 = [0.0 for _ in range(self.spec.hidden_width)]
        self.w2 = [[0.0 for _ in range(self.spec.hidden_width)] for _ in range(self.spec.second_width)]
        self.b2 = [0.0 for _ in range(self.spec.second_width)]
        self.expert_heads = [[0.0 for _ in range(self.spec.second_width)] for _ in range(self.spec.active_experts)]
        self.expert_biases = [0.0 for _ in range(self.spec.active_experts)]
        self._initialize_sparse_core(rng)
        self.changes: list[WeightChange] = []

    def _initialize_sparse_core(self, rng: Random) -> None:
        for i in range(len(FEATURES)):
            self.w1[i][i] = 1.0
            self.w2[i][i] = 1.0
        profile_adjustments = (
            {"capture_value": 0.35, "promotion_value": 0.35, "material_gain": 0.20, "multi_capture": 0.35},
            {"center_delta": 0.35, "advancement": 0.25, "mobility_delta": 0.18},
            {"exposed_piece": -0.45, "protection": 0.25, "castling": 0.18},
            {"gives_check": 0.40, "opponent_threat": -0.18, "tempo": 0.05},
        )
        for expert, adjustments in enumerate(profile_adjustments[:self.spec.active_experts]):
            for index, name in enumerate(FEATURES):
                self.expert_heads[expert][index] = INITIAL_PRIORS[name] + adjustments.get(name, 0.0)
            for index in range(len(FEATURES), self.spec.second_width):
                self.expert_heads[expert][index] = rng.uniform(-0.02, 0.02)
        for expert in range(len(profile_adjustments), self.spec.active_experts):
            self.expert_heads[expert] = [INITIAL_PRIORS.get(name, 0.0) for name in FEATURES] + [rng.uniform(-0.02, 0.02) for _ in range(self.spec.second_width - len(FEATURES))]
        for row in range(len(FEATURES), self.spec.hidden_width):
            for col in range(len(FEATURES)):
                self.w1[row][col] = rng.uniform(-0.025, 0.025)
        for row in range(len(FEATURES), self.spec.second_width):
            for col in range(self.spec.hidden_width):
                self.w2[row][col] = rng.uniform(-0.02, 0.02)

    @property
    def output_weights(self) -> dict[str, float]:
        count = len(self.expert_heads)
        return {name: sum(head[i] for head in self.expert_heads) / count for i, name in enumerate(FEATURES)}

    def _route(self, features: Sequence[float]) -> list[int]:
        route_signals = (
            abs(features[0]) + abs(features[2]) + abs(features[12]) + abs(features[13]),
            abs(features[3]) + abs(features[4]) + abs(features[10]),
            abs(features[5]) + abs(features[7]) + abs(features[8]),
            abs(features[6]) + abs(features[9]) + abs(features[15]),
        )
        return sorted(range(len(self.expert_heads)), key=lambda index: (route_signals[index % len(route_signals)], -index), reverse=True)[:min(2, len(self.expert_heads))]

    def _hidden(self, features: Sequence[float]) -> list[float]:
        if len(features) != len(FEATURES):
            raise ValueError(f"expected {len(FEATURES)} features, got {len(features)}")
        hidden1 = [tanh(sum(w * x for w, x in zip(row, features)) + bias) for row, bias in zip(self.w1, self.b1)]
        return [tanh(sum(w * x for w, x in zip(row, hidden1)) + bias) for row, bias in zip(self.w2, self.b2)]

    def score(self, features: Sequence[float]) -> float:
        hidden2 = self._hidden(features)
        routed = self._route(features)
        scores = [sum(w * x for w, x in zip(self.expert_heads[index], hidden2)) + self.expert_biases[index] for index in routed]
        return sum(scores) / len(scores)

    def probabilities(self, candidates: Sequence[Sequence[float]], temperature: float = 0.8) -> list[float]:
        if not candidates:
            return []
        if temperature <= 0:
            raise ValueError("temperature must be positive")
        logits = [self.score(features) / temperature for features in candidates]
        peak = max(logits)
        values = [exp(max(-60.0, min(0.0, value - peak))) for value in logits]
        total = sum(values)
        return [value / total for value in values]

    def adjust_from_error(self, error: str, severity: float = 1.0) -> WeightChange:
        if error not in FEEDBACK_RULES:
            raise ValueError(f"unknown feedback error: {error}")
        if not 0.0 < severity <= 5.0:
            raise ValueError("severity must be in (0, 5]")
        feature, delta = FEEDBACK_RULES[error]
        index = FEATURES.index(feature)
        before = self.output_weights[feature]
        for head in self.expert_heads:
            head[index] = max(-5.0, min(5.0, head[index] + delta * severity))
        after = self.output_weights[feature]
        change = WeightChange(error, feature, before, after)
        self.changes.append(change)
        return change

    def policy_gradient(self, candidate_features: Sequence[Sequence[float]], chosen_index: int, reward: float, learning_rate: float = 0.015, temperature: float = 0.8) -> list[list[float]]:
        if not candidate_features:
            raise ValueError("candidate_features cannot be empty")
        if not 0 <= chosen_index < len(candidate_features):
            raise IndexError("chosen_index outside candidate list")
        if not -1.0 <= reward <= 1.0:
            raise ValueError("reward must be between -1 and 1")
        if learning_rate <= 0 or temperature <= 0:
            raise ValueError("learning_rate and temperature must be positive")
        probabilities = self.probabilities(candidate_features, temperature)
        gradient = [[0.0 for _ in range(self.spec.second_width)] for _ in self.expert_heads]
        for candidate_index, (features, probability) in enumerate(zip(candidate_features, probabilities)):
            coefficient = ((1.0 if candidate_index == chosen_index else 0.0) - probability) * learning_rate * reward / temperature
            if coefficient == 0.0:
                continue
            hidden = self._hidden(features)
            routed = self._route(features)
            for expert in routed:
                scale = coefficient / len(routed)
                for index, activation in enumerate(hidden):
                    gradient[expert][index] += scale * activation
        return gradient

    def apply_output_gradient(self, gradient: Sequence[Sequence[float]]) -> None:
        if len(gradient) != len(self.expert_heads) or any(len(row) != self.spec.second_width for row in gradient):
            raise ValueError("gradient shape does not match expert output heads")
        for expert, row in enumerate(gradient):
            for index, value in enumerate(row):
                self.expert_heads[expert][index] = max(-5.0, min(5.0, self.expert_heads[expert][index] + value))

    def clone(self) -> SparsePolicyNetwork:
        clone = SparsePolicyNetwork(self.spec)
        clone.w1 = [row[:] for row in self.w1]
        clone.b1 = self.b1[:]
        clone.w2 = [row[:] for row in self.w2]
        clone.b2 = self.b2[:]
        clone.expert_heads = [head[:] for head in self.expert_heads]
        clone.expert_biases = self.expert_biases[:]
        clone.changes = self.changes[:]
        return clone

    def load_output_weights(self, values: dict[str, float]) -> None:
        unknown = set(values) - set(FEATURES)
        if unknown:
            raise ValueError(f"unknown features: {sorted(unknown)}")
        for name, value in values.items():
            if not -5.0 <= float(value) <= 5.0:
                raise ValueError(f"weight outside allowed range: {name}")
            for head in self.expert_heads:
                head[FEATURES.index(name)] = float(value)

    def diagnostics(self) -> dict[str, object]:
        return {
            "requested_topology": f"{self.spec.requested_layers}x{self.spec.requested_width}",
            "requested_dense_parameters": self.spec.requested_dense_parameters,
            "runtime_topology": f"{self.spec.input_features}-{self.spec.hidden_width}-{self.spec.second_width}-{len(self.expert_heads)}-expert-heads",
            "runtime_parameters": self.spec.active_parameters,
            "active_experts": len(self.expert_heads),
            "router_active_experts_per_action": min(2, len(self.expert_heads)),
            "output_weights": self.output_weights,
            "manual_changes": len(self.changes),
        }
