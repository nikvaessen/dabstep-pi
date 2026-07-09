# dabstep-pi

Run the [`adyen/dabstep`](https://huggingface.co/datasets/adyen/dabstep) benchmark with the [`pi`](https://github.com/earendil-works/pi) agent harness on any supported OpenRouter model. 
Each task runs in an ephemeral [`smolvm`](https://github.com/smol-machines/smolvm) sandbox so the agent can inspect benchmark context files without direct access to the host environment.

## Requirements

Install these on the host:

- `just`
- `python3`
- `git` and `git-lfs` for downloading DABStep inputs
- `docker` or `podman` for building the `pi` runtime image archive
- `smolvm` for sandboxed task execution

`pi` itself is installed inside the runtime image built from `Dockerfile.pi`; a host `pi` install is only needed if you run `tools/run_task.sh --no-smolvm`.

## Setup

1. Configure your OpenRouter API key:

   ```bash
   cp .env.example .env
   # edit .env and set OPENROUTER_API_KEY
   ```

   If you use `direnv`, `.envrc` loads `.env` automatically. Otherwise, export the variable in your shell.

2. Download benchmark inputs:

   ```bash
   just download-dabstep
   ```

   This calls `scripts/download_dabstep.sh` and writes task/context files to `data/dabstep/`.

3. Build the `pi` image archive used by `smolvm`:

   ```bash
   just build-pi-image
   ```

   The build script auto-detects `docker` or `podman`. Override with `PI_CONTAINER_RUNTIME=podman` if needed.

## Running tasks

Note: the current implementation only runs tasks from `dev.jsonl`, which include reference answers.

Run one development task:

```bash
just run-dev-task 'deepseek/deepseek-v4-pro' off 0
```

Run all development tasks with 4 parallel jobs:

```bash
just run-dev 'deepseek/deepseek-v4-pro' off 4
```

Run outputs are written to `runs/<model>/<thinking>/<task-id>/<timestamp>/`, including the rendered prompt, system prompt, `pi` JSON session log, extracted answer, and job status. A run is only accepted as `ok` if the session contains a `FINAL_ANSWER:` line.

Inspect reference answers against model predictions:

```bash
tools/inspect_answers.py 'deepseek/deepseek-v4-pro' xhigh --filter incorrect --format detail
```

## Outcomes

I ran the 10 `dev.jsonl` tasks with DeepSeek V4 Pro:

| Model                   | Thinking | Correct | Total | Accuracy | Easy | Hard | Avg cost/task | Total cost | Turns min/avg/max |
|-------------------------|----------|--------:|------:|---------:|-----:|-----:|--------------:|-----------:|------------------:|
| DeepSeek V4 Pro         | off      |       6 |    10 |    60.0% |  1/3 |  5/7 |         $0.04 |      $0.37 |    4 / 14.80 / 30 |
| DeepSeek V4 Pro         | xhigh    |       6 |    10 |    60.0% |  1/3 |  5/7 |         $0.09 |      $0.85 |    5 / 19.40 / 34 |


## AI disclosure 

This repo was written with [`pi`](https://github.com/earendil-works/pi) and GPT-5.5.

