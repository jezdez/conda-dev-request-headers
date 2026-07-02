# AGENTS.md

## Project Rules

- Use only conda's public plugin APIs (`conda.plugins.hookimpl` and
  `conda.plugins.types.CondaRequestHeader`) for conda integration.
- Keep the plugin import path lightweight; avoid optional imports or IO at
  module import time.
- Do not log header values, environment variable contents, tokens, or other
  secrets.
- Validate header names and values before yielding them to conda.
- Prefer stdlib over new dependencies.
- Keep tests as plain pytest functions. Use fixtures and `monkeypatch`; do not
  use `unittest.mock`.
- Use modern type annotations and `from __future__ import annotations` in Python
  modules.
- Run `pixi run -e test pytest`, `pixi run ruff check`, and
  `pixi run ruff format --check` after code changes.
