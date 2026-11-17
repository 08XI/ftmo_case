# Software factory: a hand-off protocol with provenance

A software factory here is a contract, not a pipeline. Planner, implementer, reviewer and human approvers hand work to each other through typed files in git. A hash-chained ledger records every hand-off: who, which prompt and model, what changed. `factory verify` checks the chain and the policy, locally and in CI. Any agent runtime, or a person, can fill a role. Built for the FTMO / OANDA "Design Your Software Factory" case study.

## Quickstart

Python 3.11+.

    python -m venv .venv
    source .venv/Scripts/activate          # Windows Git Bash; use .venv/bin/activate elsewhere
    pip install -e ".[dev]"
    python -m pytest -q

Demo (full script and the tamper demo: [demo/README.md](demo/README.md)). Run it from a clean `main` with `FACTORY_USER` set to your GitHub login. The offline fallback replays recorded role outputs:

    export FACTORY_RUNTIME=fake FACTORY_FAKE_DIR=demo/fake
    factory new "Cancel remaining quantity of partially filled orders" \
      --goal "A partially filled order can be cancelled; filled quantity is kept; FILLED stays terminal." --id T-001
    factory run planner
    factory approve-plan
    factory run implementer      # twice
    factory run reviewer
    factory status
    factory verify

With the live runtime, leave those two variables unset (needs the `claude` CLI). `factory pr` pushes the branch and opens a PR through `gh`.

## Repo map

| Path | Content |
|---|---|
| `factory/` | CLI, ledger, verify, workflow, runtimes, role prompts and tool policies |
| `spec/` | `PROTOCOL.md` and generated JSON Schemas |
| `.factory/roles/` | Role prompts (hashed into the ledger) |
| `.factory/tasks/` | Task folders, created at runtime |
| `orders/`, `tests/` | Sample order-handling module; `tests/invariants/` is protected |
| `demo/` | Demo script and recorded fake-runtime outputs |
| `evals/` | Reviewer eval: seeded invariant bugs |
| `.github/workflows/factory-verify.yml` | CI: verify, tests, gitleaks |

## Docs

- [Design](docs/plans/2026-11-16-handoff-protocol-design.md)
- [Protocol](spec/PROTOCOL.md)
- [Presentation](docs/presentation.md)
- [Build log](BUILD_LOG.md)
