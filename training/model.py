import math
from dataclasses import asdict, dataclass

import torch
from torch import nn
from torch.nn import functional as F


@dataclass(frozen=True)
class ModelConfig:
    vocab_size: int = 257
    max_seq_len: int = 128
    d_model: int = 256
    n_layers: int = 2
    n_heads: int = 4
    d_ff: int = 1024
    dropout: float = 0.1

    def validate(self):
        if self.vocab_size < 257:
            raise ValueError("vocab_size must be at least 257 for byte tokens and EOS.")
        if self.max_seq_len < 8 or self.max_seq_len > 2048:
            raise ValueError("max_seq_len must be between 8 and 2048.")
        if self.d_model < 32 or self.d_model % self.n_heads:
            raise ValueError("d_model must be at least 32 and divisible by n_heads.")
        if self.n_layers < 1 or self.n_layers > 24:
            raise ValueError("n_layers must be between 1 and 24.")
        if self.n_heads < 1 or self.n_heads > 32:
            raise ValueError("n_heads must be between 1 and 32.")
        if self.d_ff < self.d_model:
            raise ValueError("d_ff must not be smaller than d_model.")
        if not 0 <= self.dropout < 1:
            raise ValueError("dropout must be in [0, 1).")


class ByteTokenizer:
    eos_id = 256
    vocab_size = 257

    def encode(self, text, add_eos=False):
        result = list(text.encode("utf-8"))
        if add_eos:
            result.append(self.eos_id)
        return result

    def decode(self, token_ids, skip_special_tokens=True):
        raw = bytearray()
        for token_id in token_ids:
            token_id = int(token_id)
            if token_id == self.eos_id and skip_special_tokens:
                continue
            if 0 <= token_id <= 255:
                raw.append(token_id)
        return raw.decode("utf-8", errors="replace")


class CausalSelfAttention(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.n_heads = config.n_heads
        self.head_dim = config.d_model // config.n_heads
        self.qkv = nn.Linear(config.d_model, 3 * config.d_model, bias=True)
        self.output = nn.Linear(config.d_model, config.d_model, bias=True)
        self.attention_dropout = config.dropout
        self.residual_dropout = nn.Dropout(config.dropout)

    def forward(self, x):
        batch_size, seq_len, width = x.shape
        q, k, v = self.qkv(x).split(width, dim=-1)
        q = q.view(batch_size, seq_len, self.n_heads, self.head_dim).transpose(1, 2)
        k = k.view(batch_size, seq_len, self.n_heads, self.head_dim).transpose(1, 2)
        v = v.view(batch_size, seq_len, self.n_heads, self.head_dim).transpose(1, 2)
        attended = F.scaled_dot_product_attention(
            q,
            k,
            v,
            is_causal=True,
            dropout_p=self.attention_dropout if self.training else 0.0,
        )
        attended = attended.transpose(1, 2).contiguous().view(batch_size, seq_len, width)
        return self.residual_dropout(self.output(attended))


class FeedForward(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(config.d_model, config.d_ff),
            nn.GELU(),
            nn.Linear(config.d_ff, config.d_model),
            nn.Dropout(config.dropout),
        )

    def forward(self, x):
        return self.layers(x)


class TransformerBlock(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.norm_attention = nn.LayerNorm(config.d_model)
        self.attention = CausalSelfAttention(config)
        self.norm_feed_forward = nn.LayerNorm(config.d_model)
        self.feed_forward = FeedForward(config)

    def forward(self, x):
        x = x + self.attention(self.norm_attention(x))
        return x + self.feed_forward(self.norm_feed_forward(x))


class KodexGPT(nn.Module):
    def __init__(self, config=None):
        super().__init__()
        self.config = config or ModelConfig()
        self.config.validate()
        self.token_embedding = nn.Embedding(self.config.vocab_size, self.config.d_model)
        self.position_embedding = nn.Embedding(self.config.max_seq_len, self.config.d_model)
        self.input_dropout = nn.Dropout(self.config.dropout)
        self.blocks = nn.ModuleList([TransformerBlock(self.config) for _ in range(self.config.n_layers)])
        self.final_norm = nn.LayerNorm(self.config.d_model)
        self.apply(self._initialize_weights)

    @staticmethod
    def _initialize_weights(module):
        if isinstance(module, nn.Linear):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def parameter_count(self):
        return sum(parameter.numel() for parameter in self.parameters() if parameter.requires_grad)

    def forward(self, token_ids, targets=None):
        batch_size, seq_len = token_ids.shape
        if seq_len > self.config.max_seq_len:
            raise ValueError("Input sequence exceeds max_seq_len.")
        positions = torch.arange(seq_len, device=token_ids.device)
        hidden = self.token_embedding(token_ids) + self.position_embedding(positions)[None, :, :]
        hidden = self.input_dropout(hidden)
        for block in self.blocks:
            hidden = block(hidden)
        hidden = self.final_norm(hidden)
        logits = F.linear(hidden, self.token_embedding.weight)
        loss = None
        if targets is not None:
            loss = F.cross_entropy(logits.reshape(-1, logits.size(-1)), targets.reshape(-1))
        return logits, loss

    @torch.no_grad()
    def generate(self, token_ids, max_new_tokens=80, temperature=0.8, top_k=40):
        if not 0 < temperature <= 2:
            raise ValueError("temperature must be in (0, 2].")
        self.eval()
        for _ in range(max_new_tokens):
            context = token_ids[:, -self.config.max_seq_len:]
            logits, _ = self(context)
            next_logits = logits[:, -1, :] / temperature
            if top_k > 0:
                count = min(int(top_k), next_logits.shape[-1])
                values, _ = torch.topk(next_logits, count)
                next_logits[next_logits < values[:, [-1]]] = -torch.inf
            probabilities = torch.softmax(next_logits, dim=-1)
            next_token = torch.multinomial(probabilities, num_samples=1)
            token_ids = torch.cat((token_ids, next_token), dim=1)
            if next_token.item() == ByteTokenizer.eos_id:
                break
        return token_ids


def count_parameters(config=None):
    model = KodexGPT(config or ModelConfig())
    count = model.parameter_count()
    del model
    return count


if __name__ == "__main__":
    config = ModelConfig()
    model = KodexGPT(config)
    print({
        "architecture": "decoder-only causal Transformer",
        "config": asdict(config),
        "trainable_parameters": model.parameter_count(),
        "minimum_target": 780000,
    })
    if model.parameter_count() <= 780000:
        raise SystemExit("Model parameter count must exceed 780,000.")
