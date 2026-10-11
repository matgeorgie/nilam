#!/usr/bin/env bash
set -euo pipefail

nilam_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
archai_dir="${ARCHAI_DIR:-${nilam_dir}/archai}"
if [[ ! -f "${archai_dir}/apps/web/next.config.ts" ]]; then
  echo "The integrated ArchAI source was not found at ${archai_dir}. Set ARCHAI_DIR to its directory." >&2
  exit 1
fi
legacy_archai="${nilam_dir}/../ArchAI 2"
if [[ "${archai_dir}" == "${nilam_dir}/archai" && -d "${legacy_archai}" ]]; then
  for dependency in .venv node_modules; do
    if [[ ! -e "${archai_dir}/${dependency}" && -e "${legacy_archai}/${dependency}" ]]; then
      ln -s "${legacy_archai}/${dependency}" "${archai_dir}/${dependency}"
    fi
  done
  for asset in \
    apps/api/archai.db \
    apps/api/app/ml/cubicasa/model_best_val_loss_var.pkl \
    apps/api/app/ml/houseganpp/checkpoints/pretrained.pth; do
    if [[ ! -e "${archai_dir}/${asset}" && -e "${legacy_archai}/${asset}" ]]; then
      ln -s "${legacy_archai}/${asset}" "${archai_dir}/${asset}"
    fi
  done
fi
for port in 8000 8001 3000; do
  if lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port ${port} is already in use. Stop that server before starting the integrated app." >&2
    exit 1
  fi
done
if [[ ! -x "${nilam_dir}/.venv-multimodal/bin/python" || ! -x "${archai_dir}/.venv/bin/python" || ! -x "${archai_dir}/node_modules/.bin/next" ]]; then
  echo "Install the Nilam and ArchAI Python/Node dependencies first. See the READMEs." >&2
  exit 1
fi
echo "Building Nilam and the home-design studio..."
(cd "${nilam_dir}/web" && npm run build)
(cd "${archai_dir}" && npm run build)

children=()
cleanup(){
  for pid in "${children[@]}"; do kill "${pid}" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

(cd "${archai_dir}/apps/api" && exec ../../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001) & children+=("$!")
(cd "${archai_dir}/apps/web" && exec ../../node_modules/.bin/next start --hostname 127.0.0.1 --port 3000) & children+=("$!")
(cd "${nilam_dir}" && PYTORCH_ENABLE_MPS_FALLBACK=1 exec .venv-multimodal/bin/python -m uvicorn kerala_land_lab.api:app --host 127.0.0.1 --port 8000) & children+=("$!")

echo "Open http://127.0.0.1:8000/ — ArchAI is available inside Nilam at /design/"
while :; do
  for pid in "${children[@]}"; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      echo "A server stopped unexpectedly; shutting down the integrated app." >&2
      exit 1
    fi
  done
  sleep 3
done
