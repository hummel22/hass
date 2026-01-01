#!/usr/bin/env bash
set -euo pipefail

CONFIG_DIR="${1:-/config}"
BUILD_FROM="${BUILD_FROM:-ghcr.io/home-assistant/amd64-base:3.19}"
IMAGE_TAG="${IMAGE_TAG:-ha-gitops-bridge:local}"

if [[ ! -d "${CONFIG_DIR}" ]]; then
  echo "Config directory not found: ${CONFIG_DIR}" >&2
  echo "Usage: $0 /path/to/config" >&2
  exit 1
fi

docker build \
  --build-arg "BUILD_FROM=${BUILD_FROM}" \
  -t "${IMAGE_TAG}" \
  .

docker run --rm \
  --name ha_gitops_bridge \
  -p 8099:8099 \
  -v "${CONFIG_DIR}:/config" \
  "${IMAGE_TAG}"
