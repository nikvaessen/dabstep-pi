#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: tools/render_task.py [render options...] | tools/run_task.sh [options] [-- extra pi args...]

Run pi on a task prompt read from stdin.

Options:
  -m, --model MODEL         OpenRouter model (required; default: PI_MODEL)
  -t, --thinking LEVEL      pi thinking level: off|minimal|low|medium|high|xhigh
                            (default: PI_THINKING or off)
  -s, --system PATH         System prompt (default: prompts/dabstep_pi_system.md)
  -n, --name NAME           pi session name (default: dabstep-task)
      --no-smolvm           Run pi directly on the host instead of in smolvm
      --smolfile PATH       Base smolvm config (default: PI_SMOLFILE or smolvm.toml)
      --smolvm-image IMAGE  Override image from the smolvm config
      --timeout SECONDS     Max wall-clock runtime per task; 0 disables
                            (default: PI_TASK_TIMEOUT or 1800)
  -h, --help                Show this help

Run logs:
  Sessions are saved as JSON under:
    runs/<model>/<thinking-mode>/<task-id>/<timestamp>/

Environment:
  PI_MODEL                  If set, passed as: --model "$PI_MODEL"
  PI_THINKING               If set, passed as: --thinking "$PI_THINKING"; otherwise off
  PI_SMOLFILE               Base smolvm config
  PI_SMOLVM_IMAGE           Optional image override for smolvm
  PI_TASK_TIMEOUT           Max wall-clock runtime per task in seconds; 0 disables

smolvm isolation:
  By default pi runs inside an ephemeral smolvm using smolvm.toml plus CLI
  volumes for /context (read-only) and /task-run (writable run directory). The
  default config limits egress to openrouter.ai.

Examples:
  tools/render_task.py -i 0 | tools/run_task.sh -m 'google/gemma-4-31b-it:free' -t off
  PI_MODEL='google/gemma-4-31b-it:free' PI_THINKING=off tools/render_task.py -i 3 | tools/run_task.sh
EOF
}

die() {
  echo "$*" >&2
  exit 2
}

abs_path() {
  local path="$1"
  if [[ "$path" == /* ]]; then
    printf '%s\n' "$path"
  else
    printf '%s\n' "$repo_root/$path"
  fi
}

sanitize_path_component() {
  local value="${1:-default}"
  printf '%s' "$value" \
    | tr '/[:space:]' '_' \
    | tr -cd 'A-Za-z0-9._@+=:-'
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -m|--model) model="${2:?missing value for $1}"; shift 2 ;;
      -t|--thinking) thinking="${2:?missing value for $1}"; shift 2 ;;
      -s|--system) system_prompt_path="${2:?missing value for $1}"; shift 2 ;;
      -n|--name) session_name="${2:?missing value for $1}"; shift 2 ;;
      --no-smolvm) use_smolvm=0; shift ;;
      --smolfile) smolfile_path="${2:?missing value for $1}"; shift 2 ;;
      --smolvm-image) smolvm_image="${2:?missing value for $1}"; shift 2 ;;
      --timeout) task_timeout="${2:?missing value for $1}"; shift 2 ;;
      -h|--help) usage; exit 0 ;;
      --) shift; extra_pi_args=("$@"); break ;;
      *) die "Unknown option: $1" ;;
    esac
  done
}

require_required_options() {
  local missing=()
  [[ -n "$model" ]] || missing+=(--model)

  if ((${#missing[@]} > 0)); then
    printf 'Missing required option(s): %s\n' "${missing[*]}" >&2
    usage >&2
    exit 2
  fi

  case "$thinking" in
    off|minimal|low|medium|high|xhigh) ;;
    *) die "Invalid thinking level: $thinking
Allowed values: off, minimal, low, medium, high, xhigh" ;;
  esac

  if [[ ! "$task_timeout" =~ ^[0-9]+$ ]]; then
    die "Invalid timeout: $task_timeout
Timeout must be an integer number of seconds, or 0 to disable."
  fi
}

read_prompt_from_stdin() {
  local first_line

  prompt="$(cat)"
  first_line="${prompt%%$'\n'*}"
  if [[ "$first_line" != "<!-- dabstep-task-id: "* || "$first_line" != *" -->" ]]; then
    die "Missing required stdin metadata: <!-- dabstep-task-id: TASK_ID -->
Render prompts with tools/render_task.py without --no-metadata."
  fi

  task_id="${first_line#<!-- dabstep-task-id: }"
  task_id="${task_id% -->}"
  [[ -n "$task_id" ]] || die "Empty task id in stdin metadata"

  if [[ "$prompt" == *$'\n'* ]]; then
    prompt="${prompt#*$'\n'}"
  else
    prompt=""
  fi
}

create_run_dir() {
  local model_dir thinking_dir task_dir timestamp

  model_dir="$(sanitize_path_component "$model")"
  thinking_dir="$(sanitize_path_component "$thinking")"
  task_dir="$(sanitize_path_component "$task_id")"
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  run_dir="runs/$model_dir/$thinking_dir/$task_dir/$timestamp"
  mkdir -p "$run_dir"
}

prepare_prompt_paths() {
  if ((use_smolvm)); then
    prompt="${prompt//data\/dabstep\/context/\/context}"
  fi
}

write_run_inputs() {
  system_prompt="$(<"$system_prompt_path")"
  printf '%s\n' "$prompt" > "$run_dir/prompt.md"
  printf '%s\n' "$system_prompt" > "$run_dir/system.md"
}

build_pi_args() {
  local session_dir="$run_dir"
  if ((use_smolvm)); then
    session_dir="/task-run"
  fi

  pi_args=(
    pi
    --print
    # Use text stdout to avoid smolvm's 32 MiB stdout frame limit. The full
    # conversation history is still saved as JSONL by --session-dir below.
    --mode text
    --approve
    --no-context-files
    --session-dir "$session_dir"
    --name "$session_name"
    --system-prompt "$system_prompt"
    --tools "read,bash,write,grep,find,ls"
    --provider openrouter
    --model "$model"
    --thinking "$thinking"
  )
  pi_args+=("${extra_pi_args[@]}")
  pi_args+=("$prompt")
}

is_local_image_ref() {
  case "$1" in
    /*|./*|../*|*.tar|*.tar.gz|*.tgz) return 0 ;;
    *) return 1 ;;
  esac
}

validate_smolvm_inputs() {
  smolfile_path="$(abs_path "$smolfile_path")"
  [[ -e "$smolfile_path" ]] || die "Missing smolvm config: $smolfile_path"

  if [[ -n "$smolvm_image" ]] && is_local_image_ref "$smolvm_image"; then
    smolvm_image="$(abs_path "$smolvm_image")"
    [[ -e "$smolvm_image" ]] || die "Missing smolvm image/archive: $smolvm_image
Build the default archive with: just build-pi-image"
  fi
}

build_command() {
  if ((use_smolvm)); then
    validate_smolvm_inputs
    pi_cmd=(
      smolvm
      machine
      run
      --smolfile "$smolfile_path"
      --volume "$repo_root/data/dabstep/context:/context:ro"
      --volume "$repo_root/$run_dir:/task-run"
    )
    if [[ -n "$smolvm_image" ]]; then
      pi_cmd+=(--image "$smolvm_image")
    fi
    pi_cmd+=(-- /bin/sh -c 'exec "$@" > /task-run/pi.stdout 2> /task-run/pi.stderr' _ "${pi_args[@]}")
  else
    pi_cmd=("${pi_args[@]}")
  fi
}

build_run_command() {
  if [[ "$task_timeout" == "0" ]]; then
    run_cmd=("${pi_cmd[@]}")
  else
    run_cmd=(timeout --kill-after=30s "$task_timeout" "${pi_cmd[@]}")
  fi
}

extract_answer() {
  python3 - "$run_dir" <<'PY'
import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])
jsonl_files = sorted(run_dir.glob("*.jsonl"))
if not jsonl_files:
    print(f"No pi JSON session log found in {run_dir}", file=sys.stderr)
    raise SystemExit(1)

answer = None
for jsonl_file in jsonl_files:
    with jsonl_file.open(encoding="utf-8") as f:
        for line in f:
            event = json.loads(line)
            message = event.get("message")
            if event.get("type") != "message" or message is None:
                continue
            if message.get("role") != "assistant":
                continue
            text = "\n".join(
                part.get("text", "")
                for part in message.get("content", [])
                if part.get("type") == "text"
            ).strip()
            for answer_line in text.splitlines():
                stripped = answer_line.strip()
                if stripped.upper().startswith("FINAL_ANSWER:"):
                    answer = stripped

if not answer:
    print("No FINAL_ANSWER line found in pi JSON session log", file=sys.stderr)
    raise SystemExit(1)

answer_path = run_dir / "answer.md"
answer_path.write_text(answer + "\n", encoding="utf-8")
print(f"Wrote answer to: {answer_path}", file=sys.stderr)
PY
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"

system_prompt_path="prompts/dabstep_pi_system.md"
session_name="dabstep-task"
task_id=""
model="${PI_MODEL:-}"
thinking="${PI_THINKING:-off}"
use_smolvm=1
smolfile_path="${PI_SMOLFILE:-smolvm.toml}"
smolvm_image="${PI_SMOLVM_IMAGE:-}"
task_timeout="${PI_TASK_TIMEOUT:-1800}"
extra_pi_args=()

prompt=""
system_prompt=""
run_dir=""
pi_args=()
pi_cmd=()
run_cmd=()

parse_args "$@"
require_required_options
cd "$repo_root"
read_prompt_from_stdin
create_run_dir
prepare_prompt_paths
write_run_inputs
build_pi_args
build_command
build_run_command

if [[ "$task_timeout" == "0" ]]; then
  echo "Saving pi run under: $run_dir (timeout disabled)" >&2
else
  echo "Saving pi run under: $run_dir (timeout ${task_timeout}s)" >&2
fi
if ((use_smolvm)); then
  command_stdout="$run_dir/smolvm.stdout"
  command_stderr="$run_dir/smolvm.stderr"
else
  command_stdout="$run_dir/pi.stdout"
  command_stderr="$run_dir/pi.stderr"
fi

if "${run_cmd[@]}" >"$command_stdout" 2>"$command_stderr"; then
  pi_status=0
else
  pi_status=$?
  if ((pi_status == 124)) && [[ "$task_timeout" != "0" ]]; then
    printf 'pi timed out after %s seconds. See %s and %s\n' \
      "$task_timeout" "$command_stdout" "$command_stderr" >&2
  else
    printf 'pi failed with exit code %d. See %s and %s\n' \
      "$pi_status" "$command_stdout" "$command_stderr" >&2
  fi
  if [[ -s "$command_stderr" ]]; then
    tail -n 40 "$command_stderr" >&2 || true
  fi
  if [[ -s "$run_dir/pi.stderr" && "$run_dir/pi.stderr" != "$command_stderr" ]]; then
    printf 'Guest pi stderr tail (%s):\n' "$run_dir/pi.stderr" >&2
    tail -n 40 "$run_dir/pi.stderr" >&2 || true
  fi
fi

if extract_answer; then
  answer_status=0
else
  answer_status=$?
fi

if ((pi_status != 0 || answer_status != 0)); then
  status="failed"
else
  status="ok"
fi
printf '{"status":"%s","pi_status":%d,"answer_status":%d}\n' \
  "$status" "$pi_status" "$answer_status" > "$run_dir/status.json"

if ((pi_status != 0)); then
  exit "$pi_status"
fi
exit "$answer_status"
