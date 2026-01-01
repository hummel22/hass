#!/usr/bin/env bash
set -euo pipefail

# Build and run the add-on locally with a bind-mounted /config.
# Usage: ./startup.sh /path/to/config
# Optional env vars:
#   BUILD_FROM: Home Assistant base image (default: ghcr.io/home-assistant/amd64-base:3.19)
#   IMAGE_TAG: Docker image tag for the built add-on (default: ha-gitops-bridge:local)

CONFIG_DIR="${1:-/config}"
BUILD_FROM="${BUILD_FROM:-ghcr.io/home-assistant/amd64-base:3.19}"
IMAGE_TAG="${IMAGE_TAG:-ha-gitops-bridge:local}"

if [[ ! -d "${CONFIG_DIR}" ]]; then
  echo "Config directory not found: ${CONFIG_DIR}" >&2
  echo "Usage: $0 /path/to/config" >&2
  exit 1
fi

# Build the add-on image with the expected HA base.
docker build \
  --build-arg "BUILD_FROM=${BUILD_FROM}" \
  -t "${IMAGE_TAG}" \
  .

# Run with /config mounted and the UI exposed on localhost:8099.
docker run --rm \
  --name ha_gitops_bridge \
  -p 8099:8099 \
  -v "${CONFIG_DIR}:/config" \
  "${IMAGE_TAG}"
