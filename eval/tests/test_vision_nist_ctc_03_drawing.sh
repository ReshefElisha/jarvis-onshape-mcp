#!/bin/bash
# Run vision-decompose on nist_ctc_03_drawing and print the structured spec.
exec "$(dirname "$0")/_run_vision.sh" nist_ctc_03_drawing "${1:-30}"
