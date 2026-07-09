#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
image_name="${PI_SMOLVM_DOCKER_IMAGE:-dabstep-pi:latest}"
tar_path="${PI_SMOLVM_IMAGE:-$repo_root/.pi-task-work/dabstep-pi.tar}"
container_runtime="${PI_CONTAINER_RUNTIME:-}"

if [[ -z "$container_runtime" ]]; then
  if command -v docker >/dev/null 2>&1; then
    container_runtime="docker"
  elif command -v podman >/dev/null 2>&1; then
    container_runtime="podman"
  else
    printf 'Error: install docker or podman, or set PI_CONTAINER_RUNTIME.\n' >&2
    exit 1
  fi
fi

if [[ "$tar_path" != /* ]]; then
  tar_path="$repo_root/$tar_path"
fi

mkdir -p "$(dirname -- "$tar_path")"
rm -f -- "$tar_path"

"$container_runtime" build -f "$repo_root/Dockerfile.pi" -t "$image_name" "$repo_root"
"$container_runtime" save "$image_name" -o "$tar_path"

printf 'Wrote smolvm image archive: %s\n' "$tar_path" >&2
