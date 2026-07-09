#!/usr/bin/env python3
import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Literal

from summarize_accuracy import extract_final_answer, score, sort_numeric_list_answer

Row = dict[str, str]
Filter = Literal["all", "correct", "incorrect", "missing"]
OutputFormat = Literal["table", "detail", "csv", "json"]


def sanitize_path_component(value: str) -> str:
    value = re.sub(r"[/\s]", "_", value or "default")
    return "".join(char for char in value if re.match(r"[A-Za-z0-9._@+=:-]", char))


def load_tasks(path: Path) -> list[dict[str, Any]]:
    tasks = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                tasks.append(json.loads(line))
    return tasks


def read_status(run_dir: Path) -> str:
    status_path = run_dir / "status.json"
    if not status_path.exists():
        return "incomplete"
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "invalid-status"
    return str(data.get("status", "unknown"))


def iter_task_run_dirs(runs_root: Path, model_dir: str, thinking_dir: str, task_id: str):
    task_root = runs_root / model_dir / thinking_dir / task_id
    if not task_root.exists():
        return
    yield from sorted((path for path in task_root.iterdir() if path.is_dir()), reverse=True)


def latest_run(
    runs_root: Path,
    model_dir: str,
    thinking_dir: str,
    task_id: str,
    include_incomplete: bool,
) -> Path | None:
    for run_dir in iter_task_run_dirs(runs_root, model_dir, thinking_dir, task_id):
        if include_incomplete or (run_dir / "status.json").exists():
            return run_dir
    return None


def count_turns(run_dir: Path) -> int:
    turns = 0
    for jsonl_file in run_dir.glob("*.jsonl"):
        with jsonl_file.open(encoding="utf-8") as f:
            for line in f:
                event = json.loads(line)
                message = event.get("message")
                if not isinstance(message, dict):
                    continue
                if message.get("role") == "assistant" and isinstance(message.get("usage"), dict):
                    turns += 1
    return turns


def build_rows(
    tasks: list[dict[str, Any]],
    runs_root: Path,
    model: str,
    thinking: str,
    include_incomplete: bool,
) -> list[Row]:
    model_dir = sanitize_path_component(model)
    thinking_dir = sanitize_path_component(thinking)
    rows = []

    for task in tasks:
        task_id = str(task["task_id"])
        reference = sort_numeric_list_answer(str(task["answer"]))
        run_dir = latest_run(runs_root, model_dir, thinking_dir, task_id, include_incomplete)

        if run_dir is None:
            rows.append(
                {
                    "task_id": task_id,
                    "level": str(task.get("level", "unknown")),
                    "status": "missing",
                    "correct": "",
                    "turns": "",
                    "question": str(task.get("question", "")),
                    "reference": reference,
                    "prediction": "<missing run>",
                    "run_dir": "",
                }
            )
            continue

        answer_path = run_dir / "answer.md"
        prediction_text = answer_path.read_text(encoding="utf-8") if answer_path.exists() else ""
        prediction = (
            extract_final_answer(prediction_text) if prediction_text else "<missing answer>"
        )
        prediction = sort_numeric_list_answer(prediction)
        is_correct = bool(prediction_text) and score(prediction_text, reference)
        rows.append(
            {
                "task_id": task_id,
                "level": str(task.get("level", "unknown")),
                "status": read_status(run_dir),
                "correct": "yes" if is_correct else "no",
                "turns": str(count_turns(run_dir)),
                "question": str(task.get("question", "")),
                "reference": reference,
                "prediction": prediction,
                "run_dir": str(run_dir),
            }
        )

    return rows


def filter_rows(rows: list[Row], row_filter: Filter) -> list[Row]:
    if row_filter == "all":
        return rows
    if row_filter == "correct":
        return [row for row in rows if row["correct"] == "yes"]
    if row_filter == "incorrect":
        return [row for row in rows if row["correct"] == "no"]
    return [row for row in rows if row["status"] == "missing"]


def truncate(value: str, width: int) -> str:
    value = " ".join(value.split())
    if len(value) <= width:
        return value
    return value[: width - 1] + "…"


def print_table(rows: list[Row], full: bool) -> None:
    columns = ["task_id", "level", "status", "correct", "turns", "reference", "prediction"]
    display_rows = []
    for row in rows:
        display_row = row.copy()
        if not full:
            display_row["reference"] = truncate(display_row["reference"], 28)
            display_row["prediction"] = truncate(display_row["prediction"], 48)
        display_rows.append(display_row)

    widths = {
        column: max(len(column), *(len(row[column]) for row in display_rows)) for column in columns
    }
    header = " | ".join(column.ljust(widths[column]) for column in columns)
    separator = "-+-".join("-" * widths[column] for column in columns)
    print(header)
    print(separator)
    for row in display_rows:
        print(" | ".join(row[column].ljust(widths[column]) for column in columns))


def print_detail(rows: list[Row]) -> None:
    for index, row in enumerate(rows):
        if index:
            print()
        print("=" * 80)
        print(
            f"Task {row['task_id']} ({row['level']}) | "
            f"status: {row['status']} | correct: {row['correct'] or 'n/a'} | "
            f"turns: {row['turns'] or 'n/a'}"
        )
        if row["question"]:
            print()
            print("Question:")
            print(row["question"])
        print()
        print("Reference:")
        print(row["reference"])
        print()
        print("Prediction:")
        print(row["prediction"])
        if row["run_dir"]:
            print()
            print(f"Run: {row['run_dir']}")


def print_csv(rows: list[Row]) -> None:
    writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]) if rows else [])
    if rows:
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect reference answers against model predictions for one model/thinking run."
        )
    )
    parser.add_argument("model", help="Model name, e.g. deepseek/deepseek-v4-pro")
    parser.add_argument("thinking", help="Thinking level, e.g. off or xhigh")
    parser.add_argument("--tasks", default="data/dabstep/tasks/dev.jsonl", help="Task JSONL")
    parser.add_argument("--runs", default="runs", help="Runs directory")
    parser.add_argument(
        "--filter",
        choices=["all", "correct", "incorrect", "missing"],
        default="all",
        help="Rows to show",
    )
    parser.add_argument(
        "--format",
        choices=["table", "detail", "csv", "json"],
        default="table",
        help="Output format",
    )
    parser.add_argument("--full", action="store_true", help="Do not truncate table values")
    parser.add_argument(
        "--include-incomplete",
        action="store_true",
        help="Include latest run directories even when status.json is missing",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_format: OutputFormat = args.format
    row_filter: Filter = args.filter
    rows = build_rows(
        tasks=load_tasks(Path(args.tasks)),
        runs_root=Path(args.runs),
        model=args.model,
        thinking=args.thinking,
        include_incomplete=args.include_incomplete,
    )
    rows = filter_rows(rows, row_filter)

    if output_format == "json":
        print(json.dumps(rows, indent=2))
    elif output_format == "csv":
        print_csv(rows)
    elif output_format == "detail":
        print_detail(rows)
    else:
        print_table(rows, args.full)


if __name__ == "__main__":
    main()
