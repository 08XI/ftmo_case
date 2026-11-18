<p align="center">
  <img src="docs/assets/boxik.svg" width="240" alt="Boxík, the software factory mascot: a friendly cardboard box with open flaps, waving and holding a wrench">
</p>

# Software factory

Software factory is a command-line tool and hand-off protocol for code changes written by AI agents and people. Planner, implementer and reviewer roles pass work to each other through typed files in git. A hash-chained ledger records every hand-off: who acted, with which prompt and model, and what changed. `factory verify` checks the ledger against git and policy, locally and in CI.

It serves teams that must show how an agent-built change came about and who approved it. The repository also holds a small synthetic order-handling module (`orders/`) as sample code for the agents to work on. It is not real trading code. The project was built for the FTMO / OANDA "Design Your Software Factory" case study.

## Key capabilities

- **Typed hand-offs.** Tasks, plans, implementer hand-offs and reviews are validated files. Their JSON Schemas are in `spec/`.
- **Tamper-evident ledger.** Each entry records the actor, runtime, model, role-prompt hash, file hashes, cost and claimed commits, and is chained by SHA-256.
- **Enforced workflow.** Roles run in a fixed order. Agents cannot change protected paths (`tests/invariants/**` and `.factory/**` by default). Review loops are capped (default 3).
- **Independent verification.** `factory verify` runs nine checks. CI can add a tenth: approval by a human who is neither the initiator nor the plan approver.
- **Swappable runtimes.** Roles run as headless Claude Code, or from recorded outputs for offline demos and tests.

## Where it fits

![Business view of the software factory](docs/architecture/factory-business-view.svg)

The highlighted core is what this repository builds: the hand-off protocol, the `factory` CLI, the guardrails and the ledger. Agents and people fill the roles. The pull request then enters the company's existing delivery pipeline. The factory adds only its own checks to the pull request; merge and deploy stay as they are.

Dashed boxes are planned and not built: signed attestations, metrics from the ledger, policy packs and a shared prompt library, an IDE or MCP front-end, a path for non-engineers, and more agent runtimes. They come from the roadmap in [docs/presentation.md](docs/presentation.md).

## Architecture

![Container view of the software factory](docs/architecture/factory-containers.svg)

The factory has no server or database. State lives in files under `.factory/tasks/<id>/` on a git branch named `factory/<id>`.

- **Commands** are the only entry point. A developer, or GitHub Actions, runs `factory ...`.
- **Workflow engine** checks that a role may act next, builds its prompt, and records one ledger entry and one git commit per action.
- **Agent runtimes** run a role once. The Claude runtime starts `claude -p` in the repository with a per-role tool allow-list. The engine rejects changes to protected paths before it records anything.
- **Verifier** recomputes the ledger and compares it with the git history.
- **Reports and PR** print task status, build the pull-request body, and open the PR through `gh`.
- **GitHub Actions** (`.github/workflows/factory-verify.yml`) runs `factory verify` on `factory/*` pull requests, then the tests and a gitleaks scan.

The ledger is tamper-evident, not tamper-proof. [`spec/PROTOCOL.md`](spec/PROTOCOL.md) lists the limits.

## Tech stack

| Technology | Role |
|---|---|
| Python 3.11+ (CI uses 3.12) | Language |
| typer | Command-line interface |
| pydantic 2 | Data models; `spec/*.schema.json` is generated from them |
| pytest, hypothesis | Tests |
| git CLI | Storage and history |
| Claude Code CLI (`claude`) | Live agent runtime. Optional |
| GitHub CLI (`gh`) | Identity lookup and PR creation. Optional locally |

## Getting started

Prerequisites: Python 3.11 or newer and git. The offline demo needs nothing else.

Create the environment and install:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows Git Bash: source .venv/Scripts/activate
pip install -e ".[dev]"
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1` instead.

Environment variables:

| Variable | Purpose |
|---|---|
| `FACTORY_USER` | Your GitHub login. Falls back to `gh api user` |
| `FACTORY_RUNTIME` | `claude` (default) or `fake` |
| `FACTORY_FAKE_DIR` | Folder of recorded role outputs. Required when the runtime is `fake` |
| `FACTORY_MODEL` | Model alias for the `claude` runtime. Optional |

No secrets are needed for the offline demo.

Run the offline demo from a clean `main`. It creates the branch `factory/T-001` and replays the recorded role outputs in `demo/fake`. The reviewer step runs the test suite, so the sequence takes one to two minutes.

```bash
export FACTORY_USER=<your-github-login> FACTORY_RUNTIME=fake FACTORY_FAKE_DIR=demo/fake
factory new "Cancel remaining quantity of partially filled orders" \
  --goal "A partially filled order can be cancelled; filled quantity is kept; FILLED stays terminal." --id T-001
factory run planner
factory approve-plan
factory run implementer
factory run implementer
factory run reviewer
factory status
factory verify
```

In PowerShell, set the variables with `$env:FACTORY_USER = "<your-github-login>"`, and likewise for the other two, and write the `factory new` command on one line.

Expected result: `factory status` shows six ledger entries and "approved by reviewer - ready for PR", and `factory verify` ends with `RESULT: PASS`. To discard the demo, run `git checkout main` and `git branch -D factory/T-001`.

To use real agents, unset `FACTORY_RUNTIME` and `FACTORY_FAKE_DIR` and put `claude` on your `PATH`. `factory pr` then pushes the branch and opens a PR through `gh`. The script, including a tamper demo, is in [demo/README.md](demo/README.md).

## Development

```bash
python -m pytest -q                  # 75 tests, about 80 seconds
python -m factory.schemas            # regenerate spec/*.schema.json after editing factory/schemas.py
python -m evals.reviewer_eval        # live reviewer eval; calls Claude and incurs cost
```

No linter, type checker or build step is configured. Contributor and agent rules, including "never edit `tests/invariants/`" and "write the failing test first", are in [AGENTS.md](AGENTS.md).

## Further documentation

- [Protocol](spec/PROTOCOL.md): the contract, ledger fields, verify checks, limits
- [Operating the factory](docs/operating-the-factory.md): runbook for people and agents, with failure fixes
- [AGENTS.md](AGENTS.md): instructions for coding agents working in this repository
- [Design document](docs/plans/2026-11-16-handoff-protocol-design.md): rationale and decisions
- [Presentation](docs/presentation.md)
- [Demo script](demo/README.md)
- [Reviewer eval results](evals/results/latest.md)
- [Build log](BUILD_LOG.md)
