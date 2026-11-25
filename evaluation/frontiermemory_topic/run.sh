#!/usr/bin/env bash
# Replay one FrontierMemory manifest through Add, score it before and after flush, and
# have a separate-family model review the allowed splits and merges.
#
# usage: evaluation/frontiermemory_topic/run.sh <manifest.json> <out-dir> [redis-db]
#
# Environment (defaults in brackets):
#   FRONTIER_PG_DSN     local PostgreSQL 17 with pgvector and pg_trgm (required)
#   FRONTIER_REDIS      local Redis base URL [redis://127.0.0.1:6379]
#   EMBEDDING_PATH      local sentence-transformers/all-MiniLM-L6-v2 directory (required)
#   SUT_PROFILE         DeepSeek profile for Add's model [~/.deepseek.env]
#   REVIEW_PROFILE      OpenAI-compatible profile for the reviewer [~/.openai.env]
#   BUDGET_USD          hard cap for the replay's model spend [2]
#   PYTHON              interpreter with MemOS installed [python]
#   SKIP_REVIEW=1       stop after scoring
set -euo pipefail

manifest=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
mkdir -p "$2"
out=$(cd "$2" && pwd)
db=${3:-0}
repo=$(cd "$(dirname "$0")/../.." && pwd)
python=${PYTHON:-python}
: "${FRONTIER_PG_DSN:?set FRONTIER_PG_DSN}"
: "${EMBEDDING_PATH:?set EMBEDDING_PATH}"

cd "$repo"
export PYTHONPATH=".:src${PYTHONPATH:+:$PYTHONPATH}"
export FRONTIER_REDIS_URL="${FRONTIER_REDIS:-redis://127.0.0.1:6379}/$db"
export TOKENIZERS_PARALLELISM=false
export MEMOS_BASE_PATH="$out"

"$python" -m evaluation.frontiermemory_topic.replay \
  --manifest "$manifest" \
  --out "$out/replay.json" \
  --flush-out "$out/flushed.json" \
  --ledger "$out/ledger.jsonl" \
  --embedding-path "$EMBEDDING_PATH" \
  --profile "${SUT_PROFILE:-$HOME/.deepseek.env}" \
  --budget-usd "${BUDGET_USD:-2}" >"$out/stdout.log" 2>&1

for state in replay flushed; do
  "$python" -m evaluation.frontiermemory_topic.score \
    --manifest "$manifest" --results "$out/$state.json" --out "$out/score-$state.json"
done

if [[ -z "${SKIP_REVIEW:-}" ]]; then
  "$python" -m evaluation.frontiermemory_topic.review \
    --manifest "$manifest" --score "$out/score-flushed.json" --out "$out/review-flushed.json" \
    --profile "${REVIEW_PROFILE:-$HOME/.openai.env}"
fi
echo "done: $out"
