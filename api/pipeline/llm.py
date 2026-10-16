"""THE Ollama client (CLAUDE.md hard rule 3).

No other module may import an HTTP client to talk to a model - every LLM
and embedding call in this codebase goes through `LLMClient`.

`chat()` enforces the spec section 8.2 / 10.5 contract:
- Ollama `format` is the Pydantic model's JSON schema (hard rule 4);
- the reply is strictly Pydantic-validated, with one retry that shows the
  model its validation error, then `LLMOutputError` (never coerced);
- per-call timeout, total latency captured;
- exactly one `AgentRunRecord` per call goes to `run_recorder`, on success
  and on failure (hard rule 9);
- temperature is fixed per stage (hard rule 7).

Endpoint and models come from config (LLM_BASE_URL, LLM_MODEL, EMBED_MODEL),
so an open-weight hosted fallback is a config change (hard rule 1).
"""

import copy
import hashlib
import json
import time
from collections.abc import Callable
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from config import Settings, get_settings
from schemas.enums import Stage
from schemas.runs import AgentRunRecord

T = TypeVar("T", bound=BaseModel)

EMBED_DIM = 1024  # bge-m3; fixed by kb_chunks.embedding VECTOR(1024) (spec section 11)

# Hard rule 7: 0 for extraction/matching/compliance/review, low-moderate for proposal text.
STAGE_TEMPERATURE: dict[Stage, float] = {
    Stage.SCOUT: 0.0,
    Stage.MATCHING: 0.0,
    Stage.COMPLIANCE: 0.0,
    Stage.REVIEW: 0.0,
    Stage.PROPOSAL: 0.4,
}
MAX_PROPOSAL_TEMPERATURE = 0.7

_RAW_OUTPUT_LIMIT = 4000

RunRecorder = Callable[[AgentRunRecord], None]


class LLMError(Exception):
    """Base class: the stage should be marked failed."""


class LLMOutputError(LLMError):
    """Model output failed schema validation twice."""


class LLMTransportError(LLMError):
    """Ollama unreachable, timed out, or returned an unusable response."""


def json_schema_for(model: type[BaseModel]) -> dict[str, Any]:
    """The model's validation JSON schema with `$ref`s inlined.

    Inlining keeps the schema self-contained for Ollama's grammar
    conversion. Our contracts have no recursive models, so this terminates.
    """
    schema = model.model_json_schema(mode="validation")
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                target = copy.deepcopy(defs[node["$ref"].rsplit("/", 1)[-1]])
                extra = {k: v for k, v in node.items() if k != "$ref"}
                return resolve({**target, **extra})
            return {k: resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)


def _hash_request(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _truncate(text: str | None) -> str | None:
    if text is None or len(text) <= _RAW_OUTPUT_LIMIT:
        return text
    return text[:_RAW_OUTPUT_LIMIT] + "...[truncated]"


class LLMClient:
    """Synchronous Ollama client. Pass `transport=httpx.MockTransport(...)` in tests."""

    def __init__(
        self,
        run_recorder: RunRecorder,
        settings: Settings | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout_s: float | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.model = self.settings.llm_model
        self.embed_model = self.settings.embed_model
        self._record = run_recorder
        self._http = httpx.Client(
            base_url=self.settings.llm_base_url,
            timeout=timeout_s if timeout_s is not None else self.settings.llm_timeout_s,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "LLMClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- chat -------------------------------------------------------------

    def chat(
        self,
        *,
        stage: Stage,
        messages: list[dict[str, str]],
        schema: type[T],
        tender_id: int | None = None,
        temperature: float | None = None,
    ) -> T:
        """Run one schema-constrained stage call and return the validated model.

        Raises LLMOutputError (invalid twice) or LLMTransportError. Either way
        a failed AgentRunRecord has already been recorded.
        """
        temperature = self._temperature_for(stage, temperature)
        json_schema = json_schema_for(schema)
        input_hash = _hash_request(
            {
                "model": self.model,
                "stage": stage.value,
                "messages": messages,
                "schema": json_schema,
                "temperature": temperature,
            }
        )

        conversation = list(messages)
        raw: str | None = None
        error: str | None = None
        attempts = 0
        started = time.perf_counter()

        def record(ok: bool, output: BaseModel | None = None) -> None:
            self._record(
                AgentRunRecord(
                    tender_id=tender_id,
                    stage=stage,
                    model=self.model,
                    input_hash=input_hash,
                    output_json=output.model_dump(mode="json") if output is not None else None,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    ok=ok,
                    attempts=max(attempts, 1),
                    error=error,
                    raw_output=None if ok else _truncate(raw),
                )
            )

        for attempts in (1, 2):
            try:
                raw = self._post_chat(conversation, json_schema, temperature)
            except LLMTransportError as exc:
                error = str(exc)
                record(ok=False)
                raise

            try:
                result = schema.model_validate_json(raw, strict=True)
            except ValidationError as exc:
                error = f"attempt {attempts}: {exc}"
                conversation = [
                    *messages,
                    {"role": "assistant", "content": raw},
                    {
                        "role": "user",
                        "content": "Your previous reply did not match the required JSON schema:\n"
                        f"{exc}\nReply again with only JSON that matches the schema exactly.",
                    },
                ]
                continue

            error = None
            record(ok=True, output=result)
            return result

        record(ok=False)
        raise LLMOutputError(f"{stage.value}: invalid output after 2 attempts: {error}")

    def _temperature_for(self, stage: Stage, override: float | None) -> float:
        if override is None:
            return STAGE_TEMPERATURE[stage]
        if stage is not Stage.PROPOSAL and override != 0.0:
            raise ValueError(f"{stage.value} must run at temperature 0 (CLAUDE.md hard rule 7)")
        if not 0.0 <= override <= MAX_PROPOSAL_TEMPERATURE:
            raise ValueError(f"proposal temperature must be within 0..{MAX_PROPOSAL_TEMPERATURE}")
        return override

    def _post_chat(self, messages: list[dict[str, str]], json_schema: dict[str, Any], temperature: float) -> str:
        body = {
            "model": self.model,
            "messages": messages,
            "format": json_schema,
            "stream": False,
            "options": {"temperature": temperature},
        }
        data = self._post("/api/chat", body)
        try:
            content = data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LLMTransportError(f"unexpected /api/chat response shape: {data!r:.300}") from exc
        if not isinstance(content, str):
            raise LLMTransportError("/api/chat message.content is not a string")
        return content

    # --- embeddings -------------------------------------------------------

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts with EMBED_MODEL; every vector must be EMBED_DIM long.

        Not an agent stage, so no agent_runs row (ingest calls this per chunk).
        """
        if not texts:
            return []
        data = self._post("/api/embed", {"model": self.embed_model, "input": texts})
        vectors = data.get("embeddings") if isinstance(data, dict) else None
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise LLMTransportError(f"expected {len(texts)} embeddings from /api/embed")
        for vector in vectors:
            if not isinstance(vector, list) or len(vector) != EMBED_DIM:
                raise LLMTransportError(
                    f"{self.embed_model} returned a {len(vector) if isinstance(vector, list) else '?'}-dim "
                    f"vector; kb_chunks expects {EMBED_DIM}"
                )
        return vectors

    # --- transport --------------------------------------------------------

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        try:
            response = self._http.post(path, json=body)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            raise LLMTransportError(f"{path} timed out after {self._http.timeout.read}s") from exc
        except httpx.HTTPStatusError as exc:
            raise LLMTransportError(f"{path} returned HTTP {exc.response.status_code}: {exc.response.text:.300}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise LLMTransportError(f"{path} failed: {exc}") from exc
