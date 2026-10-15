#!/usr/bin/env bash
set -euo pipefail

# Pulls the Ollama models Tenderly needs (CLAUDE.md hard rule 1).
# Run this once the `ollama` service is up, e.g. after `docker compose up -d`.

CHAT_MODEL="${LLM_MODEL:-qwen2.5:7b-instruct}"
EMBED_MODEL="${EMBED_MODEL:-bge-m3}"

echo "Pulling chat model: ${CHAT_MODEL}"
docker compose exec ollama ollama pull "${CHAT_MODEL}"

echo "Pulling embedding model: ${EMBED_MODEL}"
docker compose exec ollama ollama pull "${EMBED_MODEL}"

echo "Done. Verify with: docker compose exec ollama ollama list"