"""Embed KB chunks with bge-m3 through the one LLM client (hard rule 3).

Dimension is fixed at EMBED_DIM = 1024 to match kb_chunks.embedding
VECTOR(1024); `LLMClient.embed` already rejects any other size, and this
module re-checks the count so a short batch can't misalign chunk rows.
"""

from collections.abc import Sequence

from pipeline.llm import LLMClient, LLMTransportError

BATCH_SIZE = 16


def embed_chunks(client: LLMClient, texts: Sequence[str], batch_size: int = BATCH_SIZE) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = list(texts[start : start + batch_size])
        out = client.embed(batch)
        if len(out) != len(batch):
            raise LLMTransportError(f"asked for {len(batch)} embeddings, got {len(out)}")
        vectors.extend(out)
    return vectors
