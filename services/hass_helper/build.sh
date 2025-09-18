#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

IMAGE_NAME=${1:-hass-helper}
IMAGE_TAG=${2:-latest}

DOCKERFILE_PATH="${SCRIPT_DIR}/Dockerfile"

echo "Building ${IMAGE_NAME}:${IMAGE_TAG} using ${DOCKERFILE_PATH}" >&2

docker build \
  -t "${IMAGE_NAME}:${IMAGE_TAG}" \
  -f "${DOCKERFILE_PATH}" \
  "${REPO_ROOT}"
