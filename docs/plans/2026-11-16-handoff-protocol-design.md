# Software Factory: Hand-off Protocol with Provenance — Design

Date: 2026-11-16
Context: FTMO & OANDA "Design Your Software Factory" case study (AI Engineer).
Status: approved design, ready for implementation plan.

## 1. Definition

The software factory is a **contract, not a pipeline**: a shared protocol for how
work moves between roles (planner, implementer, reviewer, human approver). Every
hand-off is typed, stored in git, and chained into a verifiable ledger.

Position on the range: near "how agents talk to each other", with one
opinionated workflow on top.

It is deliberately **not**:
- an autonomous "tasks in, production out" pipeline;
- a mandated tool — any agent runtime, or a human, can fill any role;
- a replacement for code review or CI.

## 2. Decisions

| Topic | Decision |
|---|---|
| Prototype slice | Hand-off protocol between planner, implementer, reviewer |
| Protocol form | Schema-validated files under `.factory/` in the repo |
| Agent runtime | `factory` CLI launches each role as `claude -p` with role prompt + restricted tools |
| Language | Python (typer, pydantic, pytest) |
| Deep-dive | Provenance and audit |
| Provenance mechanism | Hash-chained `ledger.jsonl` + `factory verify`; signed in-toto attestations as production roadmap |
| Output | Real GitHub PR via `gh`; GitHub Action re-runs `verify` |

## 3. Components

1. **Protocol spec (`spec/`)** — JSON Schemas for `task.json`, `plan.md`
   front-matter, `handoff-NNN.json` (done, remaining, open questions, files
   touched, test status), `review.json` (verdict, findings), and ledger entries.
   `PROTOCOL.md` is the human-readable contract.
2. **`factory` CLI (`factory/`)**
   - `factory new "<task>"` — creates task folder, records human initiator.
   - `factory run <role>` — launches role via runtime, validates output, appends ledger entry.
   - `factory approve-plan` — human plan gate.
   - `factory record --human` — records a manual human change.
   - `factory status` — task state, cost, last hand-off.
   - `factory verify` — checks the chain and policy (see §6).
   - `factory pr` — runs verify, opens GitHub PR with provenance summary.
3. **Role prompts (`.factory/roles/*.md`)** — versioned in the repo; their
   SHA-256 goes into each ledger entry. Setups no longer leave with people.
4. **GitHub Action (`.github/workflows/factory-verify.yml`)** — runs
   `factory verify` and `gitleaks` on every PR; reads PR reviews from the GitHub
   API to enforce approver rules.
5. **Sample module (`orders/`)** — synthetic Python order handling with
   invariant tests in `tests/invariants/` (e.g. filled quantity never exceeds
   order quantity; a cancelled order cannot be filled).

## 4. Walkthrough: one change

Task: *"Allow cancelling the remaining quantity of a partially filled order."*

| Step | Actor | Action | Ledger |
|---|---|---|---|
| 1 `factory new` | Human initiator | Writes task; CLI creates `.factory/tasks/T-001/task.json` with goal, protected paths (`tests/invariants/**`), initiator | #0 initiator |
| 2 `factory run planner` | Agent, read-only tools | Writes `plan.md`: steps, affected invariants, test plan | #1 planner |
| 3 `factory approve-plan` | Human initiator | Approves or edits plan — cheapest place to catch "plausible but wrong" | #2 plan approval |
| 4 `factory run implementer` | Agent, edit + test tools, no protected paths, no `.factory/` | Codes on `factory/T-001`; commits with `Factory-Task` / `Factory-Entry` trailers; must write `handoff-NNN.json` before session ends. Next session starts from plan + latest hand-off, not chat history | one entry per session |
| 5 `factory run reviewer` | Agent, fresh context, read + run tests | Sees task, plan, diff, test results — **not** implementer reasoning. Writes `review.json`. `changes_requested` → back to step 4, max N loops, then `needs-human` | #n reviewer |
| 6 `factory pr` | CLI | Runs verify locally; opens PR with body generated from ledger | — |
| 7 CI | GitHub Action | Re-runs verify + gitleaks; blocks merge on failure | — |
| 8 Approval | Human, not initiator, not plan approver | Reviews PR using `review.json` as a map, not a verdict; merges through the normal, unchanged deploy pipeline | GitHub review = final fact |

## 5. Deep-dive: provenance and audit

### Ledger entry

One JSON line in `.factory/tasks/<id>/ledger.jsonl`, written only by the CLI:

```json
{"seq":4,"task":"T-001","role":"implementer",
 "actor":{"kind":"agent","runtime":"claude-code","model":"<from runtime>"},
 "on_behalf_of":"<initiator>","role_prompt_sha256":"…",
 "inputs":{"plan.md":"<sha256>","handoff-001.json":"<sha256>"},
 "outputs":{"commits":["<sha>"],"handoff-002.json":"<sha256>"},
 "cost_usd":0.41,"tokens":{"in":0,"out":0},
 "started_at":"…","ended_at":"…","prev_hash":"…","hash":"…"}
```

- `hash = sha256(canonical_json(entry without hash))`; `prev_hash` links entries.
- Model, cost and tokens come from `claude -p --output-format json`. This gives
  the platform engineer a cost and "what it touched" view.
- Ledger appends are separate commits that touch only `.factory/`. Each entry
  claims the code commits it produced.

### Authorship and accountability

- **Accountable author**: the human initiator. An agent is never accountable.
- **Contributors**: agents, recorded with runtime, model and role-prompt hash.
- **Approver**: a different human; enforced in CI against GitHub PR reviews.
- **Audit question answered**: who asked, with which prompt and model, what
  changed, who checked it, who approved it.

### Honest limits

- Tamper-evident, not tamper-proof: someone with write access can rebuild the
  whole chain. Defences: agents cannot write `.factory/`, branch protection,
  CI recomputation.
- Model identity is self-reported by the runtime.
- Roadmap: each ledger entry maps 1:1 to a signed in-toto statement
  (sigstore / gitsign); verify then checks signatures against an identity policy.

## 6. `factory verify` checks

1. Hash chain intact; each entry valid against schema.
2. Every non-ledger commit on the branch is claimed by exactly one ledger entry
   (unclaimed human commit → fail; use `factory record --human`).
3. Recorded output hashes match files and commits.
4. No agent entry touched protected paths or `.factory/`.
5. Required roles present in order: initiator → planner → plan approval →
   implementer(s) → reviewer.
6. Last reviewer verdict is `approved`.
7. (CI only) PR approver ≠ initiator and ≠ plan approver.

## 7. Error handling

| Failure | Behaviour |
|---|---|
| Agent output fails schema | No ledger entry; run marked `failed` in `status`; error shown |
| Agent edits protected or `.factory/` path | Denied by tool restrictions; caught by verify if it happens anyway |
| Reviewer loop exceeds N | Task state → `needs-human` |
| Session dies mid-run | No hand-off written; next run resumes from last valid hand-off + `git diff` |
| `claude` / network unavailable | `FACTORY_RUNTIME=fake` replays recorded outputs |

## 8. Repository layout

```
.
  factory/            # cli.py, ledger.py, verify.py, runtime.py, schemas.py
  spec/               # JSON Schemas + PROTOCOL.md
  .factory/roles/     # planner.md, implementer.md, reviewer.md
  .factory/tasks/     # created at runtime
  orders/             # sample synthetic order-handling module
  tests/              # factory tests + orders tests; tests/invariants/ protected
  .github/workflows/factory-verify.yml
  CLAUDE.md, AGENTS.md, README.md, BUILD_LOG.md
  docs/presentation.md
```

## 9. Testing

- pytest for `ledger` and `verify`, with one tamper fixture per check: broken
  chain, orphan commit, agent edit to protected path, self-approval, skipped
  reviewer, schema-invalid hand-off.
- `FACTORY_RUNTIME=fake` replay runtime: deterministic tests and live-demo fallback
  (plus a screen recording).
- Stretch: reviewer eval with 3–5 seeded invariant-breaking diffs; report catch rate.

## 10. Out of scope

Signing, web UI, non-engineer path (sketched in presentation only), runtimes
other than `claude` and `fake`, metrics dashboard.

## 11. Presentation coverage

- Deep: point 1 (definition), point 3 (design, walkthrough, provenance deep-dive),
  point 6 (quality, security, governance).
- Brief (1–3 sentences each): people and problems; delegate/review/own;
  non-engineer apps (same protocol + approved template repos); adoption without
  a mandate (volunteer teams; senior engineer owns the protected invariants);
  first 90 days (pilot with 2 teams → signing → non-engineer path).
- Build log: delegated, reviewed, hand-written, what went wrong, time spent.

## 12. Time budget (~4 h of human time)

The case study's ~4 h is the candidate's own time. Agent runtime is tracked
separately; most of it overlaps human time (review task N while an agent builds N+1).

| Human activity | Budget |
|---|---|
| Design: brainstorm, decisions, plan review | 30 min |
| Steering and reviewing agent implementation (Tasks 1–15) | 1 h |
| Live Claude run, GitHub repo, Action, branch protection (Tasks 16–17) | 45 min |
| Presentation, build log, demo recording | 1 h 15 min |

Agent time (expected): ~1–1.5 h wall-clock for Tasks 1–15 with Sonnet subagents,
plus live role runs. `BUILD_LOG.md` records human time, agent time and agent cost
in separate columns.
