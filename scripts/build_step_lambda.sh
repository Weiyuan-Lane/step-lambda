#!/usr/bin/env bash
set -euo pipefail

# 1. Resolve repo root, wipe prior build, recreate output dirs
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${ROOT}/.build/lambda"
ZIP_PATH="${ROOT}/.build/step-lambda.zip"

rm -rf "${BUILD_DIR}" "${ZIP_PATH}"
mkdir -p "${BUILD_DIR}"

cd "${ROOT}"

# 2. Export locked prod deps from uv.lock to requirements.txt
uv export --no-dev --frozen --no-hashes --no-emit-project -o "${ROOT}/.build/requirements.txt"

# 3. Install Linux x86_64 / Python 3.14 wheels into the Lambda target dir
uv pip install \
  --python-platform x86_64-manylinux2014 \
  --python-version 3.14 \
  --target "${BUILD_DIR}" \
  -r "${ROOT}/.build/requirements.txt"

# 4. Copy application package so step_lambda.main.handler resolves
cp -R "${ROOT}/src/step_lambda" "${BUILD_DIR}/step_lambda"

# 5. Drop cached dirs to keep the zip lean
find "${BUILD_DIR}" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
find "${BUILD_DIR}" -type d -name 'tests' -exec rm -rf {} + 2>/dev/null || true
find "${BUILD_DIR}" -type d -name '*.dist-info' -path '*/step_lambda*' -prune -o -name 'tests' -print 2>/dev/null || true

# 6. Zip build dir → .build/step-lambda.zip
cd "${BUILD_DIR}"
zip -qr "${ZIP_PATH}" .
echo "Wrote ${ZIP_PATH} ($(du -h "${ZIP_PATH}" | cut -f1))"
