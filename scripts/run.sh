#!/usr/bin/env bash
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  printf '[ocr-qa] FAIL execute this script; do not source it\n' >&2
  return 2
fi
set -euo pipefail
trap 'printf "[ocr-qa] STOP status=%s line=%s; originals unchanged, checkpoints retained\n" "$?" "$LINENO" >&2' ERR
project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
runtime="${OCR_QA_VENV:-/mnt/sfs/ltj/runtime/ocr-qa}"
if [[ "${1:-}" == deploy ]]; then
  shift
  python="${OCR_QA_BOOTSTRAP_PYTHON:-python3}"
  "$python" -c 'import sys; assert sys.version_info >= (3,10), "Python3.10+ required"'
  if [[ ! -x "$runtime/bin/python" ]]; then "$python" -m venv "$runtime"; fi
  env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy -u PIP_PROXY -u PIP_EXTRA_INDEX_URL \
    PIP_CONFIG_FILE=/dev/null "$runtime/bin/python" -m pip install --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple --timeout 60 --retries 3 -r "$project/requirements.txt"
  "$runtime/bin/python" -B "$project/scripts/pipeline.py" init
  "$runtime/bin/python" -B "$project/scripts/pipeline.py" self-test
  printf '[ocr-qa] DEPLOY_PASS code/dependencies/config/self-tests only; no data/model requests\n'
else
  python="${OCR_QA_PYTHON:-$runtime/bin/python}"
  if [[ ! -x "$python" ]]; then python=python3; fi
  "$python" -B "$project/scripts/pipeline.py" "$@"
fi
