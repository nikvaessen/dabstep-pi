default:
    @just --list

# Download the DABStep task/context inputs
download-dabstep:
    @scripts/download_dabstep.sh

# Download the DABStep paper PDF/HTML
download-paper:
    @scripts/download_paper.sh

# Download benchmark inputs and paper
download-data: download-dabstep download-paper

# Build the pi container image and export it for smolvm
build-pi-image:
    @scripts/build_pi_image.sh

# Prepare data and sandbox image for local runs
setup: download-dabstep build-pi-image

# Run one task from dev.jsonl with a model and optional thinking mode
run-dev-task model thinking="off" index="0":
    tools/render_task.py --tasks data/dabstep/tasks/dev.jsonl --index {{index}} | tools/run_task.sh --model '{{model}}' --thinking '{{thinking}}'

# Run every task from dev.jsonl with a model, optional thinking mode, and parallel job count
run-dev model thinking="off" jobs="4":
    #!/usr/bin/env bash
    set -euo pipefail
    tasks="data/dabstep/tasks/dev.jsonl"
    count="$(grep -cve '^[[:space:]]*$' "$tasks")"
    jobs='{{jobs}}'
    if ! [[ "$jobs" =~ ^[1-9][0-9]*$ ]]; then
      printf 'Invalid jobs value: %s\n' "$jobs" >&2
      exit 2
    fi
    if ((count == 0)); then
      printf 'No tasks found in %s\n' "$tasks" >&2
      exit 0
    fi
    # shellcheck disable=SC2016
    seq 0 "$((count - 1))" | xargs -r -P "$jobs" -I {} bash -c '
      set -euo pipefail
      i="$1"
      count="$2"
      printf "Running dev task %s/%s with model=%s thinking=%s\n" "$((i + 1))" "$count" "$3" "$4" >&2
      tools/render_task.py --tasks "$5" --index "$i" | tools/run_task.sh --model "$3" --thinking "$4"
    ' _ {} "$count" '{{model}}' '{{thinking}}' "$tasks"
