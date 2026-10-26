---
description: Lint the files and run all tests for this project (Ruff check, Ruff format check, pytest) and report the results. Invoked as /lint-n-test.
model: haiku
disable-model-invocation: true
---

# Lint and Test

Run the project's lint and test checks and report exactly what happened. This is a check only: do not edit, fix, format, commit, or push anything.

## Steps

Run these from the repository root, in order, with `uv` (never `pip` or a separate virtualenv). Run all of them even if an earlier one fails, so the report is complete.

1. `uv sync --locked`
2. `uv run ruff check .`
3. `uv run ruff format --check .`
4. `uv run pytest -q`

Do not set `SECOND_BRAIN_LIVE`. The opt-in live test must stay skipped; it needs a running Ollama and private credentials, and it is not part of this skill.

## Report

Keep it short. Give:

1. **Overall:** `PASS` only if every step succeeded, otherwise `FAIL`.
2. **One line per step:** the command and its result.
   - Ruff check: "All checks passed!" or the number of findings.
   - Ruff format: "N files already formatted" or the files that would be reformatted.
   - pytest: the final summary line exactly as printed (passed, failed, skipped, warnings, time). Always mention the skipped count; one skipped test is expected (the opt-in live test).
3. **For each failure:** the first lines of the error, with `file:line` references (for Ruff findings, the rule code and message). For a failing test, the test name and the assertion line.

Report results faithfully. Never say a step passed if it did not run, and never hide skips, warnings, or failures. If a command could not run at all (for example `uv` is missing or the lock file is out of date), say so and show the error.

If anything failed, finish by asking whether the user wants the problems fixed. Do not fix them yourself.
