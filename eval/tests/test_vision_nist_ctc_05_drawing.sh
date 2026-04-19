#!/bin/bash
# Run vision-decompose on nist_ctc_05_drawing and print the structured spec.
exec "$(dirname "$0")/_run_vision.sh" nist_ctc_05_drawing "${1:-30}"
