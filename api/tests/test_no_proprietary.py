"""Hard rules 1-3 as a test: no proprietary/hosted model SDK or key anywhere, one model client."""

import re
from pathlib import Path

from config import Settings

ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()

FORBIDDEN = re.compile(
    r"openai|anthropic|cohere|voyageai|google[-_.]generativeai|vertexai|mistralai|\bgroq\b|together[-_.]?ai"
    r"|langchain|llama[-_]index|sentence[-_]transformers|huggingface[-_]hub|api-inference\.huggingface"
    r"|text-embedding-|OPENAI_API_KEY|ANTHROPIC_API_KEY|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}",
    re.I,
)
SKIP_DIRS = {"node_modules", ".next", ".venv", "__pycache__", ".git", ".cache", "tests"}


def _files():
    for pattern in ("api/**/*.py", "web/**/*.ts", "web/**/*.tsx", "web/**/*.mjs", "web/package.json", "web/bun.lock",
                    "api/pyproject.toml", "api/uv.lock", "docker-compose*.yml", ".env.example", "api/Dockerfile",
                    "web/Dockerfile", "scripts/*.sh"):
        for path in ROOT.glob(pattern):
            if path.is_file() and not (SKIP_DIRS & set(path.relative_to(ROOT).parts)):
                yield path


def test_no_proprietary_sdk_key_or_hosted_default():
    hits = []
    for path in _files():
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if FORBIDDEN.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()[:120]}")
    assert not hits, "proprietary / hosted-model reference found:\n" + "\n".join(hits)


def test_only_the_one_client_talks_to_ollama():
    offenders = [str(p.relative_to(ROOT)) for p in (ROOT / "api").rglob("*.py")
                 if p.name != "llm.py" and p != SELF and not (SKIP_DIRS & set(p.relative_to(ROOT).parts))
                 and re.search(r"/api/(chat|embed|generate)\b", p.read_text(encoding="utf-8", errors="ignore"))]
    assert offenders == [], f"model endpoint used outside pipeline/llm.py: {offenders}"


def test_defaults_are_local_open_weight():
    s = Settings(_env_file=None)
    assert s.llm_base_url.startswith(("http://localhost", "http://ollama"))
    assert s.llm_model.startswith(("qwen2.5", "llama3.1")) and s.embed_model == "bge-m3"