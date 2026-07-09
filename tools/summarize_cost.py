#!/usr/bin/env python3
import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def iter_jsonl_files(root: Path):
    yield from root.glob("**/*.jsonl")


def usage_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    message = event.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    return usage


def add_usage(total: dict[str, float], usage: dict[str, Any]) -> None:
    for key in ("input", "output", "cacheRead", "cacheWrite", "reasoning", "totalTokens"):
        value = usage.get(key, 0)
        if isinstance(value, int | float):
            total[key] += value

    cost = usage.get("cost")
    if isinstance(cost, dict):
        for key in ("input", "output", "cacheRead", "cacheWrite", "reasoning", "total"):
            value = cost.get(key, 0)
            if isinstance(value, int | float):
                total[f"cost_{key}"] += value


def run_key(jsonl_file: Path, runs_root: Path) -> tuple[str, str, str]:
    rel = jsonl_file.relative_to(runs_root)
    parts = rel.parts
    if len(parts) >= 5:
        return parts[0], parts[1], parts[2]
    return "unknown", "unknown", "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize token usage and cost from pi JSONL run logs."
    )
    parser.add_argument("root", nargs="?", default="runs", help="Runs directory to scan")
    args = parser.parse_args()

    root = Path(args.root)
    by_model_thinking: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    by_model_thinking_task: dict[tuple[str, str, str], dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )

    for jsonl_file in iter_jsonl_files(root):
        model, thinking, task = run_key(jsonl_file, root)
        with jsonl_file.open(encoding="utf-8") as f:
            for line in f:
                event = json.loads(line)
                usage = usage_from_event(event)
                if usage is None:
                    continue
                add_usage(by_model_thinking[(model, thinking)], usage)
                add_usage(by_model_thinking_task[(model, thinking, task)], usage)
                by_model_thinking[(model, thinking)]["turns"] += 1
                by_model_thinking_task[(model, thinking, task)]["turns"] += 1

    print(
        "model,thinking,tasks,total_cost,cost_per_task,cost_per_turn,avg_turns,"
        "input_cost,output_cost,cache_read_cost,reasoning_cost,total_tokens,total_turns"
    )
    for (model, thinking), total in sorted(by_model_thinking.items()):
        tasks = {task for m, t, task in by_model_thinking_task if m == model and t == thinking}
        task_count = len(tasks)
        total_turns = int(total["turns"])
        cost_per_task = total["cost_total"] / task_count if task_count else 0
        cost_per_turn = total["cost_total"] / total_turns if total_turns else 0
        avg_turns = total_turns / task_count if task_count else 0
        print(
            f"{model},{thinking},{task_count},"
            f"{total['cost_total']:.6f},{cost_per_task:.6f},{cost_per_turn:.6f},{avg_turns:.2f},"
            f"{total['cost_input']:.6f},{total['cost_output']:.6f},"
            f"{total['cost_cacheRead']:.6f},{total['cost_reasoning']:.6f},"
            f"{int(total['totalTokens'])},{total_turns}"
        )


if __name__ == "__main__":
    main()
