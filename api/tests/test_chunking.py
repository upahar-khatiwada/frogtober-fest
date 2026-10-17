import pytest

from ingest.chunking import MAX_TOKENS, MIN_TOKENS, chunk_text, count_tokens

ENGLISH = [
    f"Sentence {i} describes gravel road works, drainage and culverts completed for the municipality in ward {i % 9}."
    for i in range(400)
]
NEPALI = [f"वाक्य {i}: नगरपालिकाको वडा नं. {i % 9} मा सडक ग्राभेल तथा नाली निर्माण कार्य सम्पन्न भयो।" for i in range(300)]


def _paragraphs(sentences: list[str], per_paragraph: int = 7) -> str:
    return "\n\n".join(" ".join(sentences[i : i + per_paragraph]) for i in range(0, len(sentences), per_paragraph))


def test_count_tokens():
    assert count_tokens("") == 0
    assert count_tokens("road") == 1
    assert count_tokens("construction") == 3  # 12 chars / 4
    assert count_tokens("Rs. 1,02,000") == 1 + 1 + 1 + 1 + 1 + 1 + 1  # Rs . 1 , 02 , 000
    assert count_tokens("नेपाल") == 3  # 5 code points / 2, rounded up


def test_short_text_is_one_chunk():
    chunks = chunk_text("Tax clearance certificate for FY 2081/82.")
    assert [c.text for c in chunks] == ["Tax clearance certificate for FY 2081/82."]
    assert chunks[0].index == 0


def test_empty_text_gives_no_chunks():
    assert chunk_text("") == []
    assert chunk_text(" \n\n  ") == []


@pytest.mark.parametrize("sentences", [ENGLISH, NEPALI], ids=["english", "devanagari"])
def test_chunks_are_400_to_600_tokens_with_overlap(sentences):
    chunks = chunk_text(_paragraphs(sentences))
    assert len(chunks) > 3
    for chunk in chunks[:-1]:
        assert MIN_TOKENS <= chunk.token_count <= MAX_TOKENS
    assert chunks[-1].token_count <= MAX_TOKENS
    assert [c.index for c in chunks] == list(range(len(chunks)))
    for prev, nxt in zip(chunks, chunks[1:]):
        first_sentence = nxt.text.split("\n\n")[0].split(". ")[0].split("। ")[0]
        assert first_sentence in prev.text, "next chunk should start with the tail of the previous one"


@pytest.mark.parametrize("sentences", [ENGLISH, NEPALI], ids=["english", "devanagari"])
def test_no_text_is_lost(sentences):
    joined = "\n".join(c.text for c in chunk_text(_paragraphs(sentences)))
    for sentence in sentences:
        assert sentence in joined


def test_devanagari_is_preserved_exactly():
    text = "कर चुक्ता प्रमाणपत्र (आ.व. २०८१/८२)। मान्य अवधि: २०८३ असार मसान्त।"
    [chunk] = chunk_text(text)
    assert chunk.text == text


def test_text_without_sentence_breaks_is_still_bounded():
    blob = " ".join(f"word{i}" for i in range(5000))  # one giant "sentence"
    chunks = chunk_text(blob)
    assert len(chunks) > 1
    for chunk in chunks[:-1]:
        assert MIN_TOKENS <= chunk.token_count <= MAX_TOKENS


def test_last_chunk_may_be_short_but_others_are_not():
    chunks = chunk_text(_paragraphs(ENGLISH[:30]))
    assert len(chunks) == 2
    assert MIN_TOKENS <= chunks[0].token_count <= MAX_TOKENS
    assert 0 < chunks[1].token_count < MIN_TOKENS


def test_rejects_bad_bounds():
    with pytest.raises(ValueError):
        chunk_text("x", min_tokens=600, max_tokens=400)
    with pytest.raises(ValueError):
        chunk_text("x", overlap_tokens=500)
