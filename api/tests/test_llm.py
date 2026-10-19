import json

import httpx
import pytest

from pipeline.llm import EMBED_DIM, LLMClient, LLMOutputError, LLMTransportError, json_schema_for
from schemas import MatchAssessment, Stage, TenderRecord
from tests.conftest import FakeOllama

MESSAGES = [{"role": "user", "content": "Score this tender."}]
VALID_MATCH = '{"score": 72, "reasons": ["Road works in Jhapa match past projects"]}'


def test_valid_output_returns_model_and_records_run(make_client):
    fake, runs = FakeOllama([VALID_MATCH]), []
    result = make_client(fake, runs).chat(stage=Stage.MATCHING, messages=MESSAGES, schema=MatchAssessment, tender_id=7)

    assert result == MatchAssessment(score=72, reasons=["Road works in Jhapa match past projects"])
    body = fake.requests[0]["body"]
    assert body["model"] == "test-model"
    assert body["stream"] is False
    assert body["format"] == json_schema_for(MatchAssessment)
    assert body["options"]["temperature"] == 0.0

    [run] = runs
    assert (run.ok, run.attempts, run.stage, run.tender_id, run.model) == (True, 1, Stage.MATCHING, 7, "test-model")
    assert run.output_json == {"score": 72, "reasons": ["Road works in Jhapa match past projects"]}
    assert len(run.input_hash) == 64 and run.latency_ms >= 0 and run.error is None


def test_full_tender_record_round_trip(make_client, tender_payload):
    fake, runs = FakeOllama([json.dumps(tender_payload)]), []
    record = make_client(fake, runs).chat(stage=Stage.SCOUT, messages=MESSAGES, schema=TenderRecord)
    assert record.deadline_bs_iso == "2083-08-04"
    assert runs[0].ok


def test_invalid_then_valid_succeeds_on_retry(make_client):
    fake, runs = FakeOllama(['{"score": 150, "reasons": []}', VALID_MATCH]), []
    result = make_client(fake, runs).chat(stage=Stage.MATCHING, messages=MESSAGES, schema=MatchAssessment)

    assert result.score == 72
    assert len(fake.requests) == 2
    retry_messages = fake.requests[1]["body"]["messages"]
    assert retry_messages[-2] == {"role": "assistant", "content": '{"score": 150, "reasons": []}'}
    assert "did not match the required JSON schema" in retry_messages[-1]["content"]
    [run] = runs
    assert run.ok and run.attempts == 2


def test_malformed_output_retries_once_then_fails(make_client):
    fake, runs = FakeOllama(["not json at all", '{"score": "high"}', "never sent"]), []
    client = make_client(fake, runs)

    with pytest.raises(LLMOutputError):
        client.chat(stage=Stage.MATCHING, messages=MESSAGES, schema=MatchAssessment)

    assert len(fake.requests) == 2  # exactly one retry
    [run] = runs
    assert run.ok is False
    assert run.attempts == 2
    assert run.output_json is None
    assert run.raw_output == '{"score": "high"}'
    assert "attempt 2" in run.error


def test_string_number_is_not_silently_coerced(make_client):
    fake, runs = FakeOllama(['{"score": "72", "reasons": ["x"]}'] * 2), []
    with pytest.raises(LLMOutputError):
        make_client(fake, runs).chat(stage=Stage.MATCHING, messages=MESSAGES, schema=MatchAssessment)


def test_bad_nepal_enum_from_model_fails(make_client, tender_payload):
    tender_payload["procurement_type"] = "construction"
    fake, runs = FakeOllama([json.dumps(tender_payload)] * 2), []
    with pytest.raises(LLMOutputError):
        make_client(fake, runs).chat(stage=Stage.SCOUT, messages=MESSAGES, schema=TenderRecord)
    assert runs[0].ok is False


def test_timeout_records_failed_run(settings):
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    runs = []
    with LLMClient(runs.append, settings, transport=httpx.MockTransport(handler), timeout_s=0.01) as client:
        with pytest.raises(LLMTransportError, match="timed out"):
            client.chat(stage=Stage.REVIEW, messages=MESSAGES, schema=MatchAssessment)
    [run] = runs
    assert run.ok is False and run.attempts == 1 and "timed out" in run.error


def test_http_error_is_transport_error(settings):
    runs = []
    transport = httpx.MockTransport(lambda r: httpx.Response(500, text="model not found"))
    with LLMClient(runs.append, settings, transport=transport) as client:
        with pytest.raises(LLMTransportError, match="HTTP 500"):
            client.chat(stage=Stage.SCOUT, messages=MESSAGES, schema=MatchAssessment)
    assert runs[0].ok is False


def test_temperature_rules(make_client):
    fake, runs = FakeOllama([VALID_MATCH, VALID_MATCH]), []
    client = make_client(fake, runs)
    with pytest.raises(ValueError):
        client.chat(stage=Stage.COMPLIANCE, messages=MESSAGES, schema=MatchAssessment, temperature=0.3)
    with pytest.raises(ValueError):
        client.chat(stage=Stage.PROPOSAL, messages=MESSAGES, schema=MatchAssessment, temperature=1.2)

    client.chat(stage=Stage.PROPOSAL, messages=MESSAGES, schema=MatchAssessment)
    client.chat(stage=Stage.PROPOSAL, messages=MESSAGES, schema=MatchAssessment, temperature=0.6)
    assert [r["body"]["options"]["temperature"] for r in fake.requests] == [0.4, 0.6]


def test_input_hash_is_stable_and_input_sensitive(make_client):
    fake, runs = FakeOllama([VALID_MATCH] * 3), []
    client = make_client(fake, runs)
    client.chat(stage=Stage.MATCHING, messages=MESSAGES, schema=MatchAssessment)
    client.chat(stage=Stage.MATCHING, messages=MESSAGES, schema=MatchAssessment)
    client.chat(stage=Stage.MATCHING, messages=[{"role": "user", "content": "other"}], schema=MatchAssessment)
    assert runs[0].input_hash == runs[1].input_hash != runs[2].input_hash


def test_schema_has_no_refs():
    assert "$ref" not in json.dumps(json_schema_for(TenderRecord))


def test_embed_returns_vectors(make_client):
    fake, runs = FakeOllama(), []
    vectors = make_client(fake, runs).embed(["chunk one", "chunk two"])
    assert len(vectors) == 2 and all(len(v) == EMBED_DIM for v in vectors)
    assert fake.requests[0]["body"] == {"model": "test-embed", "input": ["chunk one", "chunk two"]}
    assert runs == []


def test_embed_rejects_wrong_dimension(make_client):
    with pytest.raises(LLMTransportError, match="768-dim"):
        make_client(FakeOllama(embed_dim=768), []).embed(["x"])


# --- replay cache (pre-cached demo) ---------------------------------------------------------------------------

def cached_client(settings, fake, runs, cache):
    return LLMClient(runs.append, settings, transport=httpx.MockTransport(fake.handler), cache=cache)


def test_replay_cache_records_then_replays_without_http(settings, tmp_path):
    from pipeline.llm import ReplayCache

    path = tmp_path / "cache.json"
    live, runs = FakeOllama([VALID_MATCH]), []
    first = cached_client(settings, live, runs, ReplayCache(path, record=True)).chat(
        stage=Stage.MATCHING, messages=MESSAGES, schema=MatchAssessment, tender_id=7)
    assert path.is_file() and runs[0].cached is False

    replay, runs2 = FakeOllama([]), []  # any HTTP call would pop from an empty list and blow up
    cache = ReplayCache(path)
    again = cached_client(settings, replay, runs2, cache).chat(
        stage=Stage.MATCHING, messages=MESSAGES, schema=MatchAssessment, tender_id=7)
    assert again == first and replay.requests == [] and (cache.hits, cache.misses) == (1, 0)
    [run] = runs2
    assert (run.ok, run.cached, run.model, run.input_hash) == (True, True, "test-model", runs[0].input_hash)
    assert run.output_json == runs[0].output_json


def test_replay_cache_miss_calls_the_model_and_read_only_cache_is_not_written(settings, tmp_path):
    from pipeline.llm import ReplayCache

    path = tmp_path / "cache.json"
    cache = ReplayCache(path)  # read-only
    fake, runs = FakeOllama([VALID_MATCH]), []
    cached_client(settings, fake, runs, cache).chat(stage=Stage.MATCHING, messages=MESSAGES, schema=MatchAssessment)
    assert len(fake.requests) == 1 and cache.misses == 1 and runs[0].cached is False
    assert not path.exists()


def test_replay_cache_entry_that_no_longer_validates_is_ignored(settings, tmp_path):
    from pipeline.llm import ReplayCache

    path = tmp_path / "cache.json"
    recorder = ReplayCache(path, record=True)
    cached_client(settings, FakeOllama([VALID_MATCH]), [], recorder).chat(
        stage=Stage.MATCHING, messages=MESSAGES, schema=MatchAssessment)
    data = json.loads(path.read_text(encoding="utf-8"))
    [key] = data["chat"]
    data["chat"][key]["output"]["score"] = "72"  # a string is never coerced, not even from the cache
    path.write_text(json.dumps(data), encoding="utf-8")
    fake, runs = FakeOllama([VALID_MATCH]), []
    cached_client(settings, fake, runs, ReplayCache(path)).chat(stage=Stage.MATCHING, messages=MESSAGES, schema=MatchAssessment)
    assert len(fake.requests) == 1 and runs[0].cached is False


def test_replay_cache_is_keyed_by_model(settings, tmp_path):
    from config import Settings
    from pipeline.llm import ReplayCache

    path = tmp_path / "cache.json"
    cached_client(settings, FakeOllama([VALID_MATCH]), [], ReplayCache(path, record=True)).chat(
        stage=Stage.MATCHING, messages=MESSAGES, schema=MatchAssessment)
    other = Settings(llm_base_url="http://ollama.test", llm_model="other-model", embed_model="test-embed")
    fake = FakeOllama([VALID_MATCH])
    cached_client(other, fake, [], ReplayCache(path)).chat(stage=Stage.MATCHING, messages=MESSAGES, schema=MatchAssessment)
    assert len(fake.requests) == 1


def test_replay_cache_embeddings_only_fetch_missing_texts(settings, tmp_path):
    from pipeline.llm import ReplayCache

    path = tmp_path / "cache.json"
    fake = FakeOllama(embed_fn=lambda t: [float(len(t))] + [0.0] * (EMBED_DIM - 1))
    client = cached_client(settings, fake, [], ReplayCache(path, record=True))
    client.embed(["a", "bb"])
    vectors = client.embed(["bb", "ccc", "a"])
    assert [v[0] for v in vectors] == [2.0, 3.0, 1.0]
    assert [r["body"]["input"] for r in fake.requests] == [["a", "bb"], ["ccc"]]
    replay = FakeOllama(embed_status=500)
    assert [v[0] for v in cached_client(settings, replay, [], ReplayCache(path)).embed(["ccc", "a"])] == [3.0, 1.0]
    assert replay.requests == []


def test_llm_replay_cache_setting_is_picked_up(tmp_path):
    from config import Settings
    from pipeline.llm import ReplayCache

    path = tmp_path / "cache.json"
    assert LLMClient(lambda _r: None, Settings(llm_replay_cache=str(path))).cache is None  # no file yet
    ReplayCache(path, record=True).put_embeddings({"k": [0.0]})
    client = LLMClient(lambda _r: None, Settings(llm_replay_cache=str(path)))
    assert client.cache is not None and client.cache.record is False
