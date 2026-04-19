#!/bin/bash
# Run vision-decompose on mm_2026_jan_envelope and print the structured spec.
exec "$(dirname "$0")/_run_vision.sh" mm_2026_jan_envelope "${1:-30}"
