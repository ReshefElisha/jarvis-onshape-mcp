#!/bin/bash
# Run vision-decompose on mm_2021_phase1_envelope and print the structured spec.
exec "$(dirname "$0")/_run_vision.sh" mm_2021_phase1_envelope "${1:-30}"
