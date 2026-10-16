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
