# Repository Guidelines

## Project Structure & Module Organization

This repository is at the specification stage. `docs/SPEC.md` is the source of truth for the Second Brain MCP design and security boundaries; `docs/TODO.md` tracks implementation work and release gates. `README.md` is currently a short project introduction. As implementation begins, keep Python application code in a focused package (to be established with project metadata), tests in `tests/`, and examples or deployment material in clearly named documentation/configuration files. Do not commit local databases, credentials, or machine-specific model tags.

## Build, Test, and Development Commands

There is no runnable application or build configuration yet, so no repository commands are currently available. Use Python 3.12+ and `uv` for all environment management: create the project virtual environment with `uv venv` (at the default `.venv` path), then install dependencies with `uv sync --locked` once `pyproject.toml` exists. Do not create a separate environment with `python -m venv` or another tool. Run project commands through `uv run`, including Ruff (`uv run ruff check` and the configured formatting check) and pytest (`uv run pytest`). Keep automated tests independent of Ollama, GPU hardware, network services, and external accounts by mocking backend calls; reserve live integration checks for explicit opt-in workflows. This workstation has Ollama installed with models available; use `ollama list` to discover its current tags before a live smoke test, and do not assume those tags exist on other contributors' machines.

## Coding Style & Naming Conventions

Use Python with four-space indentation, type annotations on public interfaces, and small modules organized by responsibility. Follow Ruff's configured lint and formatting rules once established. Use `snake_case` for Python modules, functions, and variables; `PascalCase` for classes; and descriptive test names such as `test_rejects_unapproved_model`. Keep configuration examples free of secrets and actual private model names.

## Testing Guidelines

The planned test framework is pytest, with `pytest-asyncio` for async behavior where needed. Place tests under `tests/` and name files `test_*.py`. Cover input validation, model allowlisting, tool-free Ollama requests, persistence, and principal isolation with mocks. Mark live Ollama/client checks clearly and never treat unrun integration gates in `docs/TODO.md` as passed.

## Security and Architecture

Preserve the specification's core boundary: Ollama receives no tool definitions and cannot access shell, files, repositories, or arbitrary network tools. Keep model selection allowlisted, derive client identity from verified authentication rather than tool arguments, and scope persisted conversations by principal. Bind local service access to loopback by default; never commit tokens, `.env` files, SQLite data, or private configuration.

## Commits and Pull Requests

The available history contains only two setup commits and does not establish a commit convention. Use short, imperative commit subjects that describe one change (for example, `Add Ollama model discovery`). Pull requests should summarize behavior and security impact, link relevant TODO/spec items, and report the checks actually run. Include configuration or client screenshots only when they clarify a user-visible change; redact secrets and private model details.
