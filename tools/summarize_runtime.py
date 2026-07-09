#!/usr/bin/env python3
import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def run_key(jsonl_file: Path, runs_root: Path) -> tuple[str, str, str, str]:
    rel = jsonl_file.relative_to(runs_root)
    parts = rel.parts
    if len(parts) >= 5:
        return parts[0], parts[1], parts[2], parts[3]
    return "unknown", "unknown", "unknown", "unknown"


def summarize_run(jsonl_file: Path) -> dict[str, float]:
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    turns = 0
    input_tokens = 0
    output_tokens = 0
    reasoning_tokens = 0
    total_tokens = 0

    with jsonl_file.open(encoding="utf-8") as f:
        for line in f:
            event: dict[str, Any] = json.loads(line)
            ts_value = event.get("timestamp")
            if isinstance(ts_value, str):
                ts = parse_ts(ts_value)
                if ts is not None:
                    first_ts = ts if first_ts is None else min(first_ts, ts)
                    last_ts = ts if last_ts is None else max(last_ts, ts)

            message = event.get("message")
            if not isinstance(message, dict):
                continue
            usage = message.get("usage")
            if not isinstance(usage, dict):
                continue
            if message.get("role") == "assistant":
                turns += 1
            input_tokens += int(usage.get("input", 0) or 0)
            output_tokens += int(usage.get("output", 0) or 0)
            reasoning_tokens += int(usage.get("reasoning", 0) or 0)
            total_tokens += int(usage.get("totalTokens", 0) or 0)

    duration_seconds = 0.0
    if first_ts is not None and last_ts is not None:
        duration_seconds = (last_ts - first_ts).total_seconds()

    return {
        "runs": 1,
        "duration_seconds": duration_seconds,
        "turns": turns,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
    }


def add(total: dict[str, float], row: dict[str, float]) -> None:
    for key, value in row.items():
        total[key] += value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize runtime, model turns, and token length from pi JSONL run logs."
    )
    parser.add_argument("root", nargs="?", default="runs", help="Runs directory to scan")
    args = parser.parse_args()

    root = Path(args.root)
    grouped: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    tasks_by_group: dict[tuple[str, str], set[str]] = defaultdict(set)

    for jsonl_file in root.glob("**/*.jsonl"):
        model, thinking, task, _timestamp = run_key(jsonl_file, root)
        summary = summarize_run(jsonl_file)
        key = (model, thinking)
        add(grouped[key], summary)
        tasks_by_group[key].add(task)

    print(
        "model,thinking,tasks,runs,total_seconds,seconds_per_task,avg_turns,"
        "tokens_per_task,output_tokens_per_task,total_turns,total_tokens,output_tokens,reasoning_tokens"
    )
    for (model, thinking), total in sorted(grouped.items()):
        task_count = len(tasks_by_group[(model, thinking)])
        seconds_per_task = total["duration_seconds"] / task_count if task_count else 0
        avg_turns = total["turns"] / task_count if task_count else 0
        tokens_per_task = total["total_tokens"] / task_count if task_count else 0
        output_tokens_per_task = total["output_tokens"] / task_count if task_count else 0
        print(
            f"{model},{thinking},{task_count},{int(total['runs'])},"
            f"{total['duration_seconds']:.2f},{seconds_per_task:.2f},{avg_turns:.2f},"
            f"{tokens_per_task:.0f},{output_tokens_per_task:.0f},"
            f"{int(total['turns'])},{int(total['total_tokens'])},"
            f"{int(total['output_tokens'])},{int(total['reasoning_tokens'])}"
        )


if __name__ == "__main__":
    main()
