#!/bin/bash
# Shared helper: run the vision sub-agent on a brief and print the result.
# Usage: _run_vision.sh <brief_id> [max_turns]
set -e
cd "$(dirname "$0")/../.."
BRIEF_ID="$1"
MAX_TURNS="${2:-30}"
if [ -z "$BRIEF_ID" ]; then
    echo "usage: $0 <brief_id> [max_turns]" >&2
    exit 1
fi
echo "=== vision sub-agent: $BRIEF_ID (max_turns=$MAX_TURNS) ==="
eval/.venv/bin/python eval/runner/run_vision.py --brief-id "$BRIEF_ID" --max-turns "$MAX_TURNS"
echo ""
echo "=== FINAL SPEC ==="
cat "eval/vision_outputs/$BRIEF_ID.txt"
