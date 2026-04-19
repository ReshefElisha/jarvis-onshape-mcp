#!/bin/bash
# Run vision-decompose on nist_ftc_09_envelope and print the structured spec.
exec "$(dirname "$0")/_run_vision.sh" nist_ftc_09_envelope "${1:-30}"
