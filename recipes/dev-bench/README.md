# Dev bench recipes

Run the DABstep `dev.jsonl` split for the small DeepSeek V4 toy experiment.

The script delegates to the root Justfile recipe:

```bash
just run-dev MODEL THINKING JOBS
```

## Usage

```bash
recipes/dev-bench/run.sh                  # runs off and xhigh thinking; jobs defaults to dev task count
recipes/dev-bench/run.sh --jobs 4         # override parallelism
recipes/dev-bench/run.sh --models recipes/dev-bench/models.txt
recipes/dev-bench/run.sh --thinking-only --thinking off
```

The default run uses both `off` and `xhigh` thinking; these are pi thinking levels passed through by `tools/run_task.sh`. 
The default model list is `recipes/dev-bench/models.txt`. 
Blank lines and `#` comments are ignored.

The default list currently includes only DeepSeek V4 Pro, with `off` and `xhigh` thinking modes.
