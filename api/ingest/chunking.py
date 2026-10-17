"""Split document text into 400-600 token chunks with overlap (spec section 10.4).

Tokens are *estimated* deterministically instead of loading bge-m3's
tokenizer: ~4 characters per token for Latin-script words, ~2 for other
scripts (Devanagari tokenises denser in XLM-R/bge-m3), 1 per punctuation
mark. Sizes are a retrieval-granularity choice, far below bge-m3's 8192
token limit, so an estimate is enough.

Invariant: every chunk except the last has min_tokens..max_tokens tokens;
the last has at most max_tokens (it may be short).
Units (sentences) longer than max - min are split on words first, which
guarantees a chunk is only closed once it has reached min_tokens.
"""

import math
import re
from dataclasses import dataclass

MIN_TOKENS = 400
MAX_TOKENS = 600
OVERLAP_TOKENS = 80

_TOKEN = re.compile(r"[\wऀ-ॿ]+|[^\w\s]")
# Sentence ends: . ! ? and the Devanagari danda / double danda.
_SENTENCE_END = re.compile(r"(?<=[.!?।॥])\s+")


def count_tokens(text: str) -> int:
    total = 0
    for match in _TOKEN.finditer(text):
        word = match.group()
        if len(word) == 1 and not word.isalnum():
            total += 1
        elif word.isascii():
            total += math.ceil(len(word) / 4)
        else:
            total += math.ceil(len(word) / 2)
    return total


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    token_count: int


@dataclass(frozen=True)
class _Unit:
    text: str
    tokens: int
    new_paragraph: bool


def _split_long(text: str, limit: int) -> list[str]:
    """Split on whitespace into pieces of <= limit tokens (a single over-long word is cut by characters)."""
    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for word in text.split():
        tokens = count_tokens(word)
        while tokens > limit:  # pathological: one "word" longer than limit (e.g. a base64 blob)
            cut = max(1, len(word) * limit // tokens)
            if current:
                pieces.append(" ".join(current))
                current, current_tokens = [], 0
            pieces.append(word[:cut])
            word = word[cut:]
            tokens = count_tokens(word)
        if current and current_tokens + tokens > limit:
            pieces.append(" ".join(current))
            current, current_tokens = [], 0
        current.append(word)
        current_tokens += tokens
    if current:
        pieces.append(" ".join(current))
    return pieces


def _units(text: str, max_unit: int) -> list[_Unit]:
    units: list[_Unit] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = " ".join(paragraph.split())
        if not paragraph:
            continue
        first = True
        for sentence in _SENTENCE_END.split(paragraph):
            for piece in _split_long(sentence, max_unit) if count_tokens(sentence) > max_unit else [sentence]:
                if piece:
                    units.append(_Unit(piece, count_tokens(piece), first))
                    first = False
    return units


def _join(units: list[_Unit]) -> str:
    out = ""
    for i, unit in enumerate(units):
        if i:
            out += "\n\n" if unit.new_paragraph else " "
        out += unit.text
    return out


def chunk_text(
    text: str,
    min_tokens: int = MIN_TOKENS,
    max_tokens: int = MAX_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[Chunk]:
    if not 0 < min_tokens < max_tokens or not 0 <= overlap_tokens < min_tokens:
        raise ValueError("need 0 < min_tokens < max_tokens and 0 <= overlap_tokens < min_tokens")
    units = _units(text, max_tokens - min_tokens)
    if not units:
        return []

    groups: list[list[_Unit]] = []
    current: list[_Unit] = []
    total = 0
    fresh = 0  # units in `current` not carried over as overlap
    for unit in units:
        if fresh and total + unit.tokens > max_tokens:
            groups.append(current)
            carry: list[_Unit] = []
            carried = 0
            for prev in reversed(current):
                if carried + prev.tokens > overlap_tokens or len(carry) + 1 >= len(current):
                    break
                carry.insert(0, prev)
                carried += prev.tokens
            current, total, fresh = carry, carried, 0
        current.append(unit)
        total += unit.tokens
        fresh += 1
    groups.append(current)

    chunks = []
    for i, group in enumerate(groups):
        body = _join(group)
        chunks.append(Chunk(index=i, text=body, token_count=count_tokens(body)))
    return chunks
