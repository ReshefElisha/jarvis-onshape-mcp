#!/bin/bash
# Run vision-decompose on mm_2009_phase1_drawing and print the structured spec.
exec "$(dirname "$0")/_run_vision.sh" mm_2009_phase1_drawing "${1:-30}"
