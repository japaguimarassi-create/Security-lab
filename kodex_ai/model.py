from __future__ import annotations

from dataclasses import asdict, dataclass

import torch
from torch import nn
from torch.nn import functional as F


@dataclass(frozen=True)
class ModelConfig:
    vocab_size: int = 1024
    block_size: int = 128
    n_layer: int = 4
    n_head: int = 6
    n_embd: int = 192
    n_ff: int = 768
    dropout: float = 0.1

    def validate(self) -> None:
        if self.vocab_size < 256:
            raise ValueError("vocab_size must be at least 256 for byte-level fallback tokens")
        if self.block_size < 8:
            raise ValueError("block_size must be at least 8")
        if self.n_layer < 1 or self.n_head < 1:
            raise ValueError("n_layer and n_head must be positive")
        if self.n_embd < 16 or self.n_embd % self.n_head:
            raise ValueError("n_embd must be >=16 and divisible by n_head")
        if self.n_ff < self.n_embd:
            raise ValueError("n_ff must be >= n_embd")
        if not 0 <= self.dropout < 1:
            raise ValueError("dropout must be in [0, 1)")

    def to_dict(self) -> dict:
        return asdict(self)


class CausalBlock(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.norm_attn = nn.LayerNorm(config.n_embd)
        self.attention = nn.MultiheadAttention(
            config.n_embd,
            config.n_head,
            dropout=config.dropout,
            batch_first=True,
        )
        self.norm_mlp = nn.LayerNorm(config.n_embd)
        self.mlp = nn.Sequential(
            nn.Linear(config.n_embd, config.n_ff),
            nn.GELU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.n_ff, config.n_embd),
            nn.Dropout(config.dropout),
        )

    def forward(self, hidden: torch.Tensor) -> torch.Tensor:
        length = hidden.shape[1]
        mask = torch.triu(
            torch.ones(length, length, device=hidden.device, dtype=torch.bool),
            diagonal=1,
        )
        normalized = self.norm_attn(hidden)
        attended, _ = self.attention(
            normalized,
            normalized,
            normalized,
            attn_mask=mask,
            need_weights=False,
        )
        hidden = hidden + attended
        return hidden + self.mlp(self.norm_mlp(hidden))


class KodexTransformer(nn.Module):
    """Small decoder-only transformer trained with next-token prediction."""

    def __init__(self, config: ModelConfig | None = None) -> None:
        super().__init__()
        self.config = config or ModelConfig()
        self.config.validate()
        self.token_embedding = nn.Embedding(self.config.vocab_size, self.config.n_embd)
        self.position_embedding = nn.Embedding(self.config.block_size, self.config.n_embd)
        self.blocks = nn.ModuleList([CausalBlock(self.config) for _ in range(self.config.n_layer)])
        self.final_norm = nn.LayerNorm(self.config.n_embd)
        self.output_bias = nn.Parameter(torch.zeros(self.config.vocab_size))
        self.dropout = nn.Dropout(self.config.dropout)
        self.apply(self._initialize)
        self.output_bias.data.zero_()

    @staticmethod
    def _initialize(module: nn.Module) -> None:
        if isinstance(module, nn.Linear):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def forward(
        self,
        token_ids: torch.Tensor,
        targets: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor | None]:
        if token_ids.ndim != 2:
            raise ValueError("token_ids must have shape [batch, sequence]")
        if token_ids.shape[1] > self.config.block_size:
            raise ValueError("sequence exceeds configured block_size")
        positions = torch.arange(token_ids.shape[1], device=token_ids.device)
        hidden = self.token_embedding(token_ids) + self.position_embedding(positions)[None, :, :]
        hidden = self.dropout(hidden)
        for block in self.blocks:
            hidden = block(hidden)
        hidden = self.final_norm(hidden)
        logits = F.linear(hidden, self.token_embedding.weight, self.output_bias)
        loss = None
        if targets is not None:
            loss = F.cross_entropy(logits.reshape(-1, logits.shape[-1]), targets.reshape(-1))
        return logits, loss

    @torch.inference_mode()
    def generate(
        self,
        token_ids: torch.Tensor,
        max_new_tokens: int = 80,
        temperature: float = 0.8,
        top_k: int = 40,
    ) -> torch.Tensor:
        if temperature <= 0:
            raise ValueError("temperature must be positive")
        was_training = self.training
        self.eval()
        try:
            for _ in range(max(0, max_new_tokens)):
                context = token_ids[:, -self.config.block_size :]
                logits, _ = self(context)
                next_logits = logits[:, -1, :] / temperature
                if 0 < top_k < next_logits.shape[-1]:
                    threshold = torch.topk(next_logits, top_k, dim=-1).values[:, -1, None]
                    next_logits = next_logits.masked_fill(next_logits < threshold, float("-inf"))
                probabilities = torch.softmax(next_logits, dim=-1)
                next_token = torch.multinomial(probabilities, num_samples=1)
                token_ids = torch.cat([token_ids, next_token], dim=1)
            return token_ids
        finally:
            self.train(was_training)


def parameter_count(model: nn.Module) -> int:
    return sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)


def default_parameter_count(vocab_size: int = 1024) -> int:
    config = ModelConfig(vocab_size=vocab_size)
    return parameter_count(KodexTransformer(config))
