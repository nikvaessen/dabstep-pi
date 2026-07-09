#!/usr/bin/env python3
import argparse
import csv
import json
import re
import string
from collections import defaultdict
from pathlib import Path
from typing import Any

NUM_RE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?")
ANSWER_PREFIX_RE = re.compile(r"(?is)^\s*[`*_]*(?:final[_\s-]*answer|answer)\s*(?:[:\-]|is)?\s*")
TOOL_CALL_ARTIFACT_RE = re.compile(
    r"(?s)(?:<\|tool_call|<tool_call\|>|\}\s*<tool_call\|>|^\s*\w+\s*\{|^\s*call:\w+\{)"
)


def load_tasks(path: Path) -> dict[str, dict[str, Any]]:
    tasks = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            task = json.loads(line)
            tasks[str(task["task_id"])] = task
    return tasks


def clean_text(value: str) -> str:
    value = value.strip().lower()
    value = value.replace("_", " ")
    value = value.translate(str.maketrans("", "", string.punctuation))
    return " ".join(value.split())


def strip_answer_prefix(value: str) -> str:
    return ANSWER_PREFIX_RE.sub("", value.strip()).strip("`*_ ")


def is_tool_call_artifact(value: str) -> bool:
    return TOOL_CALL_ARTIFACT_RE.search(value.strip()) is not None


def extract_final_answer(prediction: str) -> str:
    text = prediction.strip()
    patterns = [
        r"(?im)^\s*(?:final[_\s-]*answer|answer)\s*[:\-]\s*(.+?)\s*$",
        r"(?im)^\s*\*\*(?:final[_\s-]*answer|answer)\*\*\s*[:\-]\s*(.+?)\s*$",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            return strip_answer_prefix(matches[-1])
    nonempty = [line.strip() for line in text.splitlines() if line.strip()]
    if not nonempty:
        return ""
    answer = strip_answer_prefix(nonempty[-1])
    if is_tool_call_artifact(answer):
        return "<missing final answer>"
    return answer


def extract_number(value: str) -> float | None:
    match = NUM_RE.search(value.replace(",", ""))
    if not match:
        return None
    return float(match.group(0))


def numeric_list(value: str) -> list[float] | None:
    stripped = value.strip()
    if not ((stripped.startswith("[") and stripped.endswith("]")) or "," in stripped):
        return None
    stripped = stripped.strip("[]()")
    parts = [part.strip().strip("'\"") for part in stripped.split(",")]
    parts = [part for part in parts if part]
    if len(parts) <= 1:
        return None
    numbers = []
    for part in parts:
        if NUM_RE.fullmatch(part.replace(",", "")) is None:
            return None
        numbers.append(float(part.replace(",", "")))
    return sorted(numbers)


def sort_numeric_list_answer(value: str) -> str:
    numbers = numeric_list(value)
    if numbers is None:
        return value
    formatted = [
        str(int(number)) if float(number).is_integer() else str(number) for number in numbers
    ]
    return ", ".join(formatted)


def split_list(value: str) -> list[str] | None:
    stripped = value.strip()
    if not ((stripped.startswith("[") and stripped.endswith("]")) or "," in stripped):
        return None
    stripped = stripped.strip("[]()")
    parts = [part.strip().strip("'\"") for part in stripped.split(",")]
    parts = [part for part in parts if part]
    return sorted(clean_text(part) for part in parts) if len(parts) > 1 else None


def score(prediction: str, answer: str) -> bool:
    pred = extract_final_answer(prediction)

    pred_list = split_list(pred)
    answer_list = split_list(answer)
    if pred_list is not None and answer_list is not None:
        return pred_list == answer_list

    pred_num = extract_number(pred)
    answer_num = extract_number(answer)
    if pred_num is not None and answer_num is not None:
        return pred_num == answer_num

    pred_clean = clean_text(pred)
    answer_clean = clean_text(answer)
    return pred_clean == answer_clean or answer_clean in pred_clean


def iter_run_dirs(root: Path):
    for run_dir in root.glob("*/*/*/*"):
        if run_dir.is_dir():
            yield run_dir


def run_key(run_dir: Path, runs_root: Path) -> tuple[str, str, str, str]:
    rel = run_dir.relative_to(runs_root)
    model, thinking, task_id, timestamp = rel.parts[:4]
    return model, thinking, task_id, timestamp


def is_complete(run_dir: Path) -> bool:
    return (run_dir / "status.json").exists()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute accuracy from DABstep pi run answer.md files."
    )
    parser.add_argument("root", nargs="?", default="runs", help="Runs directory to scan")
    parser.add_argument(
        "--tasks", default="data/dabstep/tasks/dev.jsonl", help="Task JSONL with answers"
    )
    parser.add_argument("--details", default=None, help="Optional CSV path for per-run scores")
    args = parser.parse_args()

    root = Path(args.root)
    tasks = load_tasks(Path(args.tasks))
    rows = []
    grouped: dict[tuple[str, str], list[bool]] = defaultdict(list)
    grouped_by_level: dict[tuple[str, str, str], list[bool]] = defaultdict(list)

    for run_dir in iter_run_dirs(root):
        if not is_complete(run_dir):
            continue
        model, thinking, task_id, timestamp = run_key(run_dir, root)
        task = tasks.get(task_id)
        if task is None:
            continue
        answer_file = run_dir / "answer.md"
        if answer_file.exists():
            prediction = answer_file.read_text(encoding="utf-8")
            correct = score(prediction, str(task["answer"]))
        else:
            prediction = ""
            correct = False
        level = str(task.get("level", "unknown"))
        grouped[(model, thinking)].append(correct)
        grouped_by_level[(model, thinking, level)].append(correct)
        rows.append(
            {
                "model": model,
                "thinking": thinking,
                "task_id": task_id,
                "timestamp": timestamp,
                "level": level,
                "correct": int(correct),
                "answer": task["answer"],
                "prediction": extract_final_answer(prediction)
                if prediction
                else "<missing answer>",
            }
        )

    print("model,thinking,level,correct,total,accuracy")
    for (model, thinking), results in sorted(grouped.items()):
        correct = sum(results)
        total = len(results)
        print(f"{model},{thinking},all,{correct},{total},{correct / total:.4f}")
        for level in sorted(
            level for m, t, level in grouped_by_level if m == model and t == thinking
        ):
            level_results = grouped_by_level[(model, thinking, level)]
            level_correct = sum(level_results)
            level_total = len(level_results)
            print(
                f"{model},{thinking},{level},{level_correct},{level_total},"
                f"{level_correct / level_total:.4f}"
            )

    if args.details:
        with Path(args.details).open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else [])
            if rows:
                writer.writeheader()
                writer.writerows(rows)


if __name__ == "__main__":
    main()
