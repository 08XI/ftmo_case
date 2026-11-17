# AGENTS.md

Instructions for any coding agent (Claude Code, Codex, Cursor) in this repository,
whether you are building the factory or playing a factory role (planner, implementer, reviewer).

## What is here
- `factory/`: the `factory` CLI, a hand-off protocol with a hash-chained ledger. Contract: `spec/PROTOCOL.md`.
- `orders/`: a synthetic order-handling module that factory agents work on. Not real trading code.
- `spec/*.schema.json`: generated from `factory/schemas.py` by `python -m factory.schemas`. Never edit by hand.
- `.factory/roles/`: role prompts. They are hashed into every ledger entry; changing them changes agent behaviour.
- `.factory/tasks/`: task folders. Only the `factory` CLI writes here.

## Commands
- Install: `python -m venv .venv` then `.venv/Scripts/python -m pip install -e ".[dev]"` (Windows) or `.venv/bin/python ...` (Linux/macOS).
- Test: `python -m pytest -q`
- Regenerate schemas: `python -m factory.schemas`

## Rules
- Never edit `tests/invariants/`. Humans own the invariants.
- Never edit `.factory/tasks/` by hand.
- Files are LF (`.gitattributes`). Ledger hashes depend on exact bytes.
- Test first: write the failing test, see it fail, then implement.
- Python 3.11+, type hints, no new dependencies without a reason.
