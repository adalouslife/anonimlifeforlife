#!/usr/bin/env bash
set -euo pipefail

echo "==> Booting RunPod worker"
echo " Python:  $(python --version 2>&1 || true)"
echo " PWD:     $(pwd)"
echo " Files:   $(ls -1)"
echo " VPS_BASE: ${VPS_BASE:-<unset>}"
if [[ -n "${VPS_TOKEN:-}" ]]; then
  echo " VPS_TOKEN: **** (set)"
else
  echo " VPS_TOKEN: <unset>"
fi
echo " RUNPOD_TEST: ${RUNPOD_TEST:-<unset>}"
echo " HTTP_TIMEOUT_S: ${HTTP_TIMEOUT_S:-300}"

# Fail fast if missing envs (except when test mode is enabled)
if [[ "${RUNPOD_TEST:-}" != "1" ]]; then
  [[ -n "${VPS_BASE:-}" ]] || { echo "FATAL: VPS_BASE is required"; exit 64; }
  [[ -n "${VPS_TOKEN:-}" ]] || { echo "FATAL: VPS_TOKEN is required"; exit 64; }
fi

# Smoke import
python - <<'PY'
import importlib
for m in ("runpod","requests"):
    importlib.import_module(m)
print("[OK] imports")
PY

echo "==> Starting runpod worker"
exec python -u -m runpod
