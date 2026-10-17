import httpx
import pytest

from ingest.embed import embed_chunks
from pipeline.llm import EMBED_DIM, LLMTransportError
from tests.conftest import FakeOllama, bag_of_words_vector


def test_embed_chunks_returns_one_1024_dim_vector_per_chunk(make_client):
    fake = FakeOllama(embed_fn=bag_of_words_vector)
    runs: list = []
    client = make_client(fake, runs)
    texts = [f"chunk {i} नेपाल" for i in range(5)]

    vectors = embed_chunks(client, texts, batch_size=2)

    assert EMBED_DIM == 1024
    assert len(vectors) == 5
    assert all(len(v) == 1024 for v in vectors)
    assert [len(r["body"]["input"]) for r in fake.requests] == [2, 2, 1]
    assert fake.requests[0]["body"]["model"] == "test-embed"
    assert runs == []  # embeddings are not an agent stage


def test_wrong_dimension_is_rejected(make_client):
    client = make_client(FakeOllama(embed_dim=768), [])
    with pytest.raises(LLMTransportError, match="768-dim"):
        embed_chunks(client, ["a"])


def test_short_batch_is_rejected(settings):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[0.0] * 1024]})

    from pipeline.llm import LLMClient

    with LLMClient(lambda _r: None, settings, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(LLMTransportError):
            embed_chunks(client, ["a", "b"])


def test_empty_input_makes_no_calls(make_client):
    fake = FakeOllama()
    assert embed_chunks(make_client(fake, []), []) == []
    assert fake.requests == []
