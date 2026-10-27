#!/usr/bin/env bash
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  printf '[ocr-sync] FAIL execute, do not source\n' >&2
  return 2
fi
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
python3 -B "$root/scripts/sync.py"
