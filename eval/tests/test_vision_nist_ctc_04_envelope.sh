#!/bin/bash
# Run vision-decompose on nist_ctc_04_envelope and print the structured spec.
exec "$(dirname "$0")/_run_vision.sh" nist_ctc_04_envelope "${1:-30}"
