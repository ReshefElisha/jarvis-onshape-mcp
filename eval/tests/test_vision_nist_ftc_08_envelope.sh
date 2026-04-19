#!/bin/bash
# Run vision-decompose on nist_ftc_08_envelope and print the structured spec.
exec "$(dirname "$0")/_run_vision.sh" nist_ftc_08_envelope "${1:-30}"
