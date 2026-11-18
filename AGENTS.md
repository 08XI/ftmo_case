# AGENTS.md

Instructions for any coding agent (Claude Code, Codex, Cursor) in this repository. `CLAUDE.md` imports this file.

Know which of three situations you are in:
1. **Building the factory** (changing `factory/`, `spec/`, tests, docs): follow all sections below.
2. **Playing a factory role** (planner, implementer, reviewer, started by `factory run <role>`): follow your role prompt in `.factory/roles/<role>.md` and the Rules below. You cannot run `factory`; your shell is limited to `python -m pytest`.
3. **Operating the factory** (running a task end to end for a human): read [docs/operating-the-factory.md](docs/operating-the-factory.md) first.

This file is loaded by role agents too, and unlike role prompts it is not hashed into the ledger. Keep it short, accurate and free of role-specific instructions. Put operator detail in `docs/`.

## What the project is
A hand-off protocol with provenance for agent-built changes. Roles hand work to each other through typed files on a git branch `factory/<task-id>`. A hash-chained ledger (`ledger.jsonl`) records every hand-off. `factory verify` recomputes the ledger and checks it against git. Contract: `spec/PROTOCOL.md`. Overview and diagram: `README.md`.

## Map
- `factory/`: the CLI.
  - `cli.py` commands (typer) · `core.py` operations, one ledger entry and one commit each · `workflow.py` allowed role order (pure functions)
  - `ledger.py` hash chain · `verify.py` the checks · `report.py` status, PR body, `gh` PR
  - `runtime.py` Claude Code and fake runtimes · `prompts.py` prompt builder and per-role tool policy
  - `schemas.py` pydantic models, the single source of the protocol's data contract · `gitutil.py` git wrappers · `errors.py`
- `orders/`: synthetic order-handling module that factory agents work on. Not real trading code.
- `tests/factory/`: tests of the CLI. `tests/orders/`: behaviour tests. `tests/invariants/`: protected, human-owned, property-based.
- `spec/`: `PROTOCOL.md` plus JSON Schemas generated from `factory/schemas.py`. Never edit the schemas by hand.
- `.factory/roles/`: role prompts, hashed into every agent ledger entry. Changing one changes agent behaviour.
- `.factory/tasks/`: task folders. Only the `factory` CLI writes here (one exception: `plan.md` before `factory approve-plan`).
- `demo/`: recorded fake-runtime outputs. `evals/`: reviewer eval with seeded bugs. `docs/`: design, presentation, operator guide.

## Commands
- Install: `python -m venv .venv`, then `.venv/Scripts/python -m pip install -e ".[dev]"` (Windows) or `.venv/bin/python -m pip install -e ".[dev]"` (Linux/macOS).
- Test: `python -m pytest -q` (75 tests, about 80 seconds; run one file while iterating, the full suite before you finish).
- Regenerate schemas after changing `factory/schemas.py`: `python -m factory.schemas`. A drift test fails if `spec/` is stale.
- There is no linter, type checker or build step.

## Rules
- Never edit `tests/invariants/`. Humans own the invariants. If one needs to change, say so and stop.
- Never edit `.factory/tasks/` by hand, except `plan.md` before `factory approve-plan`.
- Files are LF (`.gitattributes`). Ledger hashes depend on exact bytes. Write files with LF endings.
- Test first: write the failing test, see it fail, then implement.
- Python 3.11+, type hints, no new dependencies without a reason.
- Keep `spec/PROTOCOL.md`, `factory/schemas.py` and `spec/*.schema.json` consistent. A protocol change updates all three.
- Do not run `factory new`, `run`, `approve-plan` or `record` on a task you were not asked to run. They create branches and commits.
- On a task branch: do not rebase, amend, squash or merge `main` after the ledger is written. It invalidates commit claims.
- Never print or commit secrets. The CI runs gitleaks.
- Report test results as they are. If a test fails or you did not run it, say so.

## Decisions that belong to a human
Approving a plan, approving a pull request, changing `tests/invariants/`, changing role prompts, and turning on `FACTORY_REQUIRE_APPROVAL`.
