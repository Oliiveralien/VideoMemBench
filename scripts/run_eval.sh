#!/usr/bin/env bash
set -euo pipefail
# Run from the repository root after editing the config.
python -m inference.evaluate --config "${1:-configs/evaluation.toml}"
