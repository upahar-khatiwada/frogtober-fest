# Demo replay cache

`llm_cache.json` (not committed yet: it must be recorded on a machine with Ollama) holds validated model
outputs keyed by request hash, plus embeddings. It comes from:

```
cd api && uv run python -m api.scripts.precache_demo --seed-company   # fresh DB, Ollama up
cd api && uv run python -m api.scripts.precache_demo --check          # replay only, no HTTP; exit 1 on any miss
```

With `LLM_REPLAY_CACHE` pointing here (docker-compose does this by default), the same requests are answered
from the file in milliseconds. The outputs are still schema-validated, and every agent_runs row is marked
`cached`. Anything not in the file goes to the live model.

Prompts cite KB chunk ids, so record against the KB the demo will use. A fresh DB seeded once gives the same
ids every time.
