#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def load_task(tasks_path: Path, task_id: str | None, index: int) -> dict:
    with tasks_path.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            task = json.loads(line)
            if task_id is not None:
                if str(task["task_id"]) == str(task_id):
                    return task
            elif i == index:
                return task
    if task_id is not None:
        raise SystemExit(f"Task id not found: {task_id}")
    raise SystemExit(f"Task index not found: {index}")


def render_context_files(ctx_dir: Path, ctx_render_path: Path) -> str:
    """List files in ctx_dir, rendered under ctx_render_path.

    Usually these are the same. If the rendered prompt should refer to the same
    files through a different mount/path, ctx_render_path overrides the path
    prefix shown in the prompt.
    """
    if not ctx_dir.exists():
        return f"- {ctx_render_path.as_posix()} (missing)"
    if ctx_dir.is_file():
        return f"- {ctx_render_path.as_posix()}"

    files = sorted(p for p in ctx_dir.rglob("*") if p.is_file())
    if not files:
        return "- (no files found)"

    rendered = []
    for file in files:
        rel = file.relative_to(ctx_dir)
        rendered.append(f"- {(ctx_render_path / rel).as_posix()}")
    return "\n".join(rendered)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render one factual data-analysis task prompt for pi."
    )
    parser.add_argument(
        "-t", "--tasks", default="data/dabstep/tasks/dev.jsonl", help="Path to tasks JSONL"
    )
    parser.add_argument("-T", "--task-id", default=None, help="Task id to render")
    parser.add_argument(
        "-i", "--index", type=int, default=0, help="Zero-based task index if --task-id is omitted"
    )
    parser.add_argument(
        "-c",
        "--ctx",
        dest="ctx_dir",
        default="data/dabstep/context",
        help="Directory containing context files",
    )
    parser.add_argument(
        "-r",
        "--ctx-render-path",
        dest="ctx_render_path",
        default=None,
        help=(
            "Optional path prefix to show for context files in the rendered prompt; "
            "defaults to --ctx"
        ),
    )
    parser.add_argument(
        "-p", "--template", default="prompts/dabstep_pi_task.md", help="Task prompt template"
    )
    parser.add_argument(
        "--no-metadata",
        action="store_true",
        help="Do not emit the task metadata comment line",
    )
    args = parser.parse_args()

    task = load_task(Path(args.tasks), args.task_id, args.index)
    template = Path(args.template).read_text(encoding="utf-8")
    ctx_render_path = Path(args.ctx_render_path) if args.ctx_render_path else Path(args.ctx_dir)
    prompt = template.format(
        ctx_path=ctx_render_path.as_posix(),
        context_files=render_context_files(Path(args.ctx_dir), ctx_render_path),
        question=task["question"],
        guidelines=task.get("guidelines", ""),
    )
    if not args.no_metadata:
        print(f"<!-- dabstep-task-id: {task['task_id']} -->")
    print(prompt)


if __name__ == "__main__":
    main()
