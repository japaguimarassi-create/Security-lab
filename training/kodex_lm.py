from dataclasses import asdict, dataclass

import torch
from torch import nn
from torch.nn import functional as F


@dataclass(frozen=True)
class ModelConfig:
    vocab_size: int = 256
    block_size: int = 128
    n_layer: int = 4
    n_head: int = 4
    n_embd: int = 128
    n_kv_head: int = 2
    n_experts: int = 4
    experts_per_token: int = 2
    router_aux_loss_coef: float = 0.01
    dropout: float = 0.0
    rope_theta: float = 10000.0
    initializer_range: float = 0.02


class RMSNorm(nn.Module):
    def __init__(self, dimension, eps=1e-6):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(dimension))
        self.eps = eps

    def forward(self, x):
        normalized = x.float() * torch.rsqrt(x.float().pow(2).mean(dim=-1, keepdim=True) + self.eps)
        return normalized.to(dtype=x.dtype) * self.weight


class RotaryEmbedding(nn.Module):
    def __init__(self, head_dim, theta):
        super().__init__()
        if head_dim % 2:
            raise ValueError("head dimension must be even for rotary embeddings")
        inverse_frequency = 1.0 / (theta ** (torch.arange(0, head_dim, 2, dtype=torch.float32) / head_dim))
        self.register_buffer("inverse_frequency", inverse_frequency, persistent=False)

    def forward(self, x):
        length = x.shape[-2]
        positions = torch.arange(length, device=x.device, dtype=self.inverse_frequency.dtype)
        angles = torch.outer(positions, self.inverse_frequency)
        cos = angles.cos().to(dtype=x.dtype)[None, None, :, :]
        sin = angles.sin().to(dtype=x.dtype)[None, None, :, :]
        even = x[..., 0::2]
        odd = x[..., 1::2]
        rotated = torch.stack((even * cos - odd * sin, even * sin + odd * cos), dim=-1)
        return rotated.flatten(-2)


class CausalSelfAttention(nn.Module):
    def __init__(self, config: ModelConfig):
        super().__init__()
        if config.n_embd % config.n_head != 0:
            raise ValueError("n_embd must be divisible by n_head")
        if config.n_kv_head < 1 or config.n_head % config.n_kv_head != 0:
            raise ValueError("n_kv_head must be a positive divisor of n_head")
        self.n_head = config.n_head
        self.n_kv_head = config.n_kv_head
        self.head_dim = config.n_embd // config.n_head
        if self.head_dim % 2:
            raise ValueError("n_embd / n_head must be even for rotary embeddings")
        self.q_proj = nn.Linear(config.n_embd, self.n_head * self.head_dim, bias=False)
        self.k_proj = nn.Linear(config.n_embd, self.n_kv_head * self.head_dim, bias=False)
        self.v_proj = nn.Linear(config.n_embd, self.n_kv_head * self.head_dim, bias=False)
        self.o_proj = nn.Linear(config.n_embd, config.n_embd, bias=False)
        self.rotary = RotaryEmbedding(self.head_dim, config.rope_theta)
        self.attn_dropout = config.dropout
        self.resid_dropout = nn.Dropout(config.dropout)

    def forward(self, x):
        batch, length, channels = x.shape
        q = self.q_proj(x).view(batch, length, self.n_head, self.head_dim).transpose(1, 2)
        k = self.k_proj(x).view(batch, length, self.n_kv_head, self.head_dim).transpose(1, 2)
        v = self.v_proj(x).view(batch, length, self.n_kv_head, self.head_dim).transpose(1, 2)

        q = self.rotary(q)
        k = self.rotary(k)

        if self.n_kv_head != self.n_head:
            repeat_count = self.n_head // self.n_kv_head
            k = k.repeat_interleave(repeat_count, dim=1)
            v = v.repeat_interleave(repeat_count, dim=1)

        attended = F.scaled_dot_product_attention(
            q,
            k,
            v,
            is_causal=True,
            dropout_p=self.attn_dropout if self.training else 0.0,
        )
        attended = attended.transpose(1, 2).contiguous().view(batch, length, channels)
        return self.resid_dropout(self.o_proj(attended))


class FeedForward(nn.Module):
    def __init__(self, config: ModelConfig):
        super().__init__()
        hidden_size = (8 * config.n_embd + 2) // 3
        hidden_size = ((hidden_size + 7) // 8) * 8
        self.gate_proj = nn.Linear(config.n_embd, hidden_size, bias=False)
        self.up_proj = nn.Linear(config.n_embd, hidden_size, bias=False)
        self.down_proj = nn.Linear(hidden_size, config.n_embd, bias=False)
        self.dropout = nn.Dropout(config.dropout)

    def forward(self, x):
        return self.dropout(self.down_proj(F.silu(self.gate_proj(x)) * self.up_proj(x)))


class SparseMixtureOfExperts(nn.Module):
    def __init__(self, config: ModelConfig):
        super().__init__()
        if config.n_experts < 1:
            raise ValueError("n_experts must be positive")
        if config.experts_per_token < 1 or config.experts_per_token > config.n_experts:
            raise ValueError("experts_per_token must be between 1 and n_experts")
        if config.router_aux_loss_coef < 0:
            raise ValueError("router_aux_loss_coef must be non-negative")
        self.n_experts = config.n_experts
        self.experts_per_token = config.experts_per_token
        self.router = nn.Linear(config.n_embd, config.n_experts, bias=False)
        self.experts = nn.ModuleList(FeedForward(config) for _ in range(config.n_experts))

    def forward(self, x):
        batch, length, channels = x.shape
        flat = x.reshape(-1, channels)
        probabilities = torch.softmax(self.router(flat).float(), dim=-1)
        top_probabilities, top_indices = torch.topk(probabilities, self.experts_per_token, dim=-1)
        top_probabilities = top_probabilities / top_probabilities.sum(dim=-1, keepdim=True).clamp_min(1e-9)
        output = torch.zeros_like(flat)

        for expert_id, expert in enumerate(self.experts):
            token_indices, slot_indices = (top_indices == expert_id).nonzero(as_tuple=True)
            if token_indices.numel() == 0:
                continue
            expert_output = expert(flat[token_indices])
            weights = top_probabilities[token_indices, slot_indices].to(expert_output.dtype).unsqueeze(-1)
            output = output.index_add(0, token_indices, expert_output * weights)

        if self.training:
            importance = probabilities.mean(dim=0)
            load = F.one_hot(top_indices, num_classes=self.n_experts).float().mean(dim=(0, 1))
            auxiliary_loss = self.n_experts * torch.sum(importance * load)
        else:
            auxiliary_loss = x.new_zeros(())
        return output.view(batch, length, channels), auxiliary_loss


class TransformerBlock(nn.Module):
    def __init__(self, config: ModelConfig):
        super().__init__()
        self.input_norm = RMSNorm(config.n_embd)
        self.attention = CausalSelfAttention(config)
        self.post_attention_norm = RMSNorm(config.n_embd)
        self.feed_forward = SparseMixtureOfExperts(config)

    def forward(self, x):
        x = x + self.attention(self.input_norm(x))
        feed_forward_output, auxiliary_loss = self.feed_forward(self.post_attention_norm(x))
        return x + feed_forward_output, auxiliary_loss


class KodexLanguageModel(nn.Module):
    def __init__(self, config: ModelConfig):
        super().__init__()
        if config.vocab_size < 2 or config.block_size < 2:
            raise ValueError("vocab_size and block_size must be at least 2")
        if config.n_layer < 1 or config.n_head < 1 or config.n_embd < 2:
            raise ValueError("model dimensions must be positive")
        if config.n_experts < 1 or not 1 <= config.experts_per_token <= config.n_experts:
            raise ValueError("experts_per_token must be between 1 and n_experts")
        if config.router_aux_loss_coef < 0:
            raise ValueError("router_aux_loss_coef must be non-negative")
        self.config = config
        self.token_embedding = nn.Embedding(config.vocab_size, config.n_embd)
        self.embedding_dropout = nn.Dropout(config.dropout)
        self.blocks = nn.ModuleList(TransformerBlock(config) for _ in range(config.n_layer))
        self.final_norm = RMSNorm(config.n_embd)
        self.last_aux_loss = torch.tensor(0.0)
        self.language_head = nn.Linear(config.n_embd, config.vocab_size, bias=False)
        self.apply(self._initialize_weights)
        self.language_head.weight = self.token_embedding.weight

    def _initialize_weights(self, module):
        if isinstance(module, nn.Linear):
            nn.init.normal_(module.weight, mean=0.0, std=self.config.initializer_range)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(module.weight, mean=0.0, std=self.config.initializer_range)
        if isinstance(module, (CausalSelfAttention, FeedForward)):
            output_projection = module.o_proj if isinstance(module, CausalSelfAttention) else module.down_proj
            nn.init.normal_(
                output_projection.weight,
                mean=0.0,
                std=self.config.initializer_range / (2 * self.config.n_layer) ** 0.5,
            )

    def forward(self, input_ids, targets=None):
        if input_ids.ndim != 2:
            raise ValueError("input_ids must have shape [batch, sequence]")
        if input_ids.shape[1] > self.config.block_size:
            raise ValueError("input sequence exceeds block_size")
        if input_ids.numel() and (input_ids.min() < 0 or input_ids.max() >= self.config.vocab_size):
            raise ValueError("input token ID is outside the configured vocabulary")

        x = self.embedding_dropout(self.token_embedding(input_ids))
        auxiliary_losses = []
        for block in self.blocks:
            x, auxiliary_loss = block(x)
            auxiliary_losses.append(auxiliary_loss)
        if auxiliary_losses:
            self.last_aux_loss = torch.stack(auxiliary_losses).mean()
        else:
            self.last_aux_loss = x.new_zeros(())
        x = self.final_norm(x)
        logits = self.language_head(x)
        loss = None
        if targets is not None:
            if targets.shape != input_ids.shape:
                raise ValueError("targets must have the same shape as input_ids")
            loss = F.cross_entropy(logits.reshape(-1, logits.size(-1)), targets.reshape(-1))
            if self.training:
                loss = loss + self.config.router_aux_loss_coef * self.last_aux_loss
        return logits, loss

    def parameter_count(self):
        return sum(parameter.numel() for parameter in self.parameters() if parameter.requires_grad)

    def config_dict(self):
        return asdict(self.config)


def encode_bytes(text):
    return list(text.encode("utf-8"))


def decode_bytes(token_ids):
    return bytes(int(token_id) for token_id in token_ids).decode("utf-8", errors="replace")
