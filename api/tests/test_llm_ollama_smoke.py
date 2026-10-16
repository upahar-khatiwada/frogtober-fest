"""Real-Ollama smoke test. Skipped by default; run with `uv run pytest -m ollama`.

Needs Ollama at LLM_BASE_URL with LLM_MODEL and EMBED_MODEL pulled.
On low-RAM machines, point LLM_MODEL at a smaller open-weight model
(e.g. LLM_MODEL=qwen2.5:1.5b-instruct) - this only checks the plumbing.
"""

import pytest

from pipeline.llm import EMBED_DIM, LLMClient
from schemas import MatchAssessment, Stage

pytestmark = pytest.mark.ollama


def test_real_ollama_chat_and_embed():
    runs = []
    with LLMClient(runs.append) as client:
        result = client.chat(
            stage=Stage.MATCHING,
            messages=[
                {
                    "role": "system",
                    "content": "Score how well a tender fits a company from 0 to 100 and give short reasons.",
                },
                {
                    "role": "user",
                    "content": "Company: road construction contractor in Jhapa. "
                    "Tender: gravelling of a 2 km rural road in Jhapa.",
                },
            ],
            schema=MatchAssessment,
        )
        vectors = client.embed(["Class C construction licence, renewed for FY 2083/84."])

    assert 0 <= result.score <= 100
    assert runs[0].ok
    assert len(vectors[0]) == EMBED_DIM
