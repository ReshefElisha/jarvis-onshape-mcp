#!/bin/bash
# Run vision-decompose on nist_ftc_10_drawing and print the structured spec.
exec "$(dirname "$0")/_run_vision.sh" nist_ftc_10_drawing "${1:-30}"
