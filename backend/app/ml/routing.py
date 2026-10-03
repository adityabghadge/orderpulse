"""Return routing: predict which team should handle a return from what the customer wrote.

The model is a small neural text classifier (the "fastText" design):

    words and word pairs ──> embedding per token ──> average ─┐
                                                              ├─> linear layer ──> 4 teams
    dropdown reason ───────> embedding ───────────────────────┘

It trains in seconds on a laptop CPU, predicts in well under a millisecond, and is easy to
explain. The dropdown is an input too: the model learns when to trust it and when the text
tells a different story.
"""

import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import torch
from torch import nn

from app.domain.returns import ReturnReason, Team
from app.ml.text import Vocabulary

TEAMS = [t.value for t in Team]
REASONS = [r.value for r in ReturnReason]


class RoutingNetwork(nn.Module):
    def __init__(self, vocab_size: int, embedding_dim: int = 32, reason_dim: int = 8) -> None:
        super().__init__()
        self.text = nn.EmbeddingBag(vocab_size, embedding_dim, mode="mean")
        self.reason = nn.Embedding(len(REASONS), reason_dim)
        self.classify = nn.Sequential(
            nn.Dropout(0.2), nn.Linear(embedding_dim + reason_dim, len(TEAMS))
        )

    def forward(
        self, token_ids: torch.Tensor, offsets: torch.Tensor, reason_ids: torch.Tensor
    ) -> torch.Tensor:
        features = torch.cat([self.text(token_ids, offsets), self.reason(reason_ids)], dim=1)
        return self.classify(features)


@dataclass(frozen=True)
class Route:
    team: str
    confidence: float


class ReturnRouter:
    """A trained routing model plus everything needed to use it."""

    def __init__(
        self, network: RoutingNetwork, vocab: Vocabulary, metadata: dict | None = None
    ) -> None:
        self.network = network.eval()
        self.vocab = vocab
        self.metadata = metadata or {}

    def _batch(self, texts: list[str], reasons: list[str]):
        encoded = [self.vocab.encode(t) for t in texts]
        offsets = torch.tensor([0] + [len(e) for e in encoded[:-1]]).cumsum(0)
        token_ids = torch.tensor([i for e in encoded for i in e])
        reason_ids = torch.tensor([REASONS.index(r) for r in reasons])
        return token_ids, offsets, reason_ids

    @torch.no_grad()
    def predict_many(self, texts: list[str], reasons: list[str]) -> list[Route]:
        if not texts:
            return []
        probabilities = torch.softmax(self.network(*self._batch(texts, reasons)), dim=1)
        confidence, index = probabilities.max(dim=1)
        return [
            Route(TEAMS[i], round(float(c), 4))
            for i, c in zip(index.tolist(), confidence.tolist(), strict=True)
        ]

    def predict(self, text: str, reason: str) -> Route:
        return self.predict_many([text], [reason])[0]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "state_dict": self.network.state_dict(),
                "vocab": self.vocab.tokens,
                "metadata": self.metadata,
            },
            path,
        )

    @classmethod
    def load(cls, path: Path) -> "ReturnRouter":
        # weights_only=True refuses to unpickle arbitrary Python objects from the file.
        saved = torch.load(path, weights_only=True)
        vocab = Vocabulary(saved["vocab"])
        network = RoutingNetwork(len(vocab))
        network.load_state_dict(saved["state_dict"])
        return cls(network, vocab, saved["metadata"])


def train_router(
    texts: list[str],
    reasons: list[str],
    teams: list[str],
    *,
    epochs: int = 12,
    batch_size: int = 64,
    learning_rate: float = 0.02,
    seed: int = 7,
) -> ReturnRouter:
    torch.manual_seed(seed)
    rng = random.Random(seed)
    vocab = Vocabulary.build(texts)
    router = ReturnRouter(RoutingNetwork(len(vocab)), vocab)
    network = router.network.train()
    optimizer = torch.optim.Adam(network.parameters(), lr=learning_rate)
    loss_fn = nn.CrossEntropyLoss()
    labels = [TEAMS.index(t) for t in teams]
    order = list(range(len(texts)))

    for _ in range(epochs):
        rng.shuffle(order)
        for start in range(0, len(order), batch_size):
            batch = order[start : start + batch_size]
            inputs = router._batch([texts[i] for i in batch], [reasons[i] for i in batch])
            optimizer.zero_grad()
            loss = loss_fn(network(*inputs), torch.tensor([labels[i] for i in batch]))
            loss.backward()
            optimizer.step()

    network.eval()
    router.metadata = {"trained_at": datetime.now(UTC).isoformat(), "vocab_size": len(vocab)}
    return router
