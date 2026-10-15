"""Embed chunks into pgvector via bge-m3 (spec section 11, AI_DISCLOSURE.md).

TODO (next prompt): embed_chunks(...) calling pipeline.llm.embed (the one
Ollama client - CLAUDE.md hard rule 3), storing VECTOR(1024) rows in
kb_chunks. Dimension is fixed to bge-m3's 1024 (PROGRESS.md Decisions) -
do not change without a migration.
"""