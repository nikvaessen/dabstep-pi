#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: recipes/dev-bench/run.sh [options]

Run the small DABstep dev toy experiment described in the root README.
This script delegates each model/thinking run to the repository Justfile recipe:
  just run-dev MODEL THINKING JOBS

Options:
  -m, --models PATH       Model list file (default: recipes/dev-bench/models.txt)
  -t, --thinking LEVEL    Thinking mode to run; repeatable (overrides model-list modes)
      --thinking-only     Clear default/model-list thinking modes before applying --thinking
  -j, --jobs N            Parallel dev-task jobs per model (default: number of dev tasks)
  -h, --help              Show this help

Environment:
  DEV_BENCH_MODELS        Alternative model list path
  DEV_BENCH_THINKING      Comma-separated thinking modes; overrides model-list modes
  DEV_BENCH_JOBS          Alternative parallel job count
EOF
}

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
models_file="${DEV_BENCH_MODELS:-recipes/dev-bench/models.txt}"
thinking_csv="${DEV_BENCH_THINKING:-off}"
jobs="${DEV_BENCH_JOBS:-}"
IFS=, read -r -a thinking_modes <<< "$thinking_csv"
thinking_overridden=0
if [[ -n "${DEV_BENCH_THINKING:-}" ]]; then
  thinking_overridden=1
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    -m|--models) models_file="${2:?missing value for $1}"; shift 2 ;;
    -t|--thinking) thinking_modes+=("${2:?missing value for $1}"); thinking_overridden=1; shift 2 ;;
    --thinking-only) thinking_modes=(); thinking_overridden=1; shift ;;
    -j|--jobs) jobs="${2:?missing value for $1}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

cd "$repo_root"
[[ -f "$models_file" ]] || { echo "Missing model list: $models_file" >&2; exit 2; }
if [[ -z "$jobs" ]]; then
  jobs="$(grep -cve '^[[:space:]]*$' data/dabstep/tasks/dev.jsonl)"
fi

while IFS= read -r line || [[ -n "$line" ]]; do
  line="${line%%#*}"
  read -r model model_thinking_csv _ <<< "$line"
  [[ -n "$model" ]] || continue

  run_thinking_modes=("${thinking_modes[@]}")
  if [[ "$thinking_overridden" == 0 && -n "${model_thinking_csv:-}" ]]; then
    IFS=, read -r -a run_thinking_modes <<< "$model_thinking_csv"
  fi

  for thinking in "${run_thinking_modes[@]}"; do
    [[ -n "$thinking" ]] || continue
    printf '\n=== Running dev bench: model=%s thinking=%s jobs=%s ===\n' "$model" "$thinking" "$jobs" >&2
    just run-dev "$model" "$thinking" "$jobs"
  done
done < "$models_file"
