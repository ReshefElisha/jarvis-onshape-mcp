#!/bin/bash
# Run v001 twice more to get 3-sample noise floor on medium tier.
# Resets the round-robin cursor each time so we sample the same 3 briefs
# the baseline + v001 first pass used.
#
# Usage:  bash eval/run_noise_floor.sh
# Blocks until all runs complete. Expects eval/.venv and Onshape creds
# already in place. Writes each line into scoreboard.jsonl.

set -e
cd "$(dirname "$0")/.."

for i in 1 2; do
    python3 -c "
import json
from pathlib import Path
p = Path('eval/state.json')
s = json.loads(p.read_text())
s['round_robin_cursor']['medium'] = 0
p.write_text(json.dumps(s, indent=2))
"
    echo "=== v001 repeat $i/2 ==="
    eval/.venv/bin/python eval/runner/run_eval_set.py \
        --variant-id v001-plan-from-render \
        --parent-variant-id baseline \
        --mutation-description "v001 noise-floor repeat $i/2"
done

echo "=== NOISE-FLOOR SUMMARY ==="
tail -5 eval/scoreboard.jsonl | python3 -c "
import sys, json
rows = [json.loads(ln) for ln in sys.stdin if ln.strip()]
# Keep only v001 runs on medium tier.
v001 = [r for r in rows if r['variant_id'] == 'v001-plan-from-render' and r['tier'] == 'medium']
means = [r['mean_composite'] for r in v001]
print(f'v001 runs: {len(v001)}  means: {means}')
if len(means) >= 2:
    import statistics
    sd = statistics.stdev(means)
    print(f'stdev: {sd:.4f}  (2*sd = {2*sd:.4f})')
"
