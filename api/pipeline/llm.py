"""THE Ollama client (CLAUDE.md hard rule 3).

No other module may import an HTTP client to talk to a model - every LLM
and embedding call in this codebase goes through here.

TODO (next prompt):
- chat(...) -> JSON-schema-constrained call (Ollama `format` = the Pydantic
  model's JSON schema) + Pydantic validation, one retry on invalid output,
  then mark the stage "failed" - never silently coerce (hard rule 4).
- embed(...) -> bge-m3, 1024-dim, via Ollama.
- Read endpoint/model from config.get_settings() (LLM_BASE_URL, LLM_MODEL,
  EMBED_MODEL) so a hosted open-weight-only fallback is a config change,
  not a code change (hard rule 1).
"""