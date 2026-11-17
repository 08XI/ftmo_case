# Software factory: a hand-off protocol with provenance

Talk outline, 35-40 min. Sections marked "deep" get the most time. Design: [design doc](plans/2026-11-16-handoff-protocol-design.md). Contract: [PROTOCOL.md](../spec/PROTOCOL.md).

| # | Section | Min |
|---|---|---|
| 1 | Definition (deep) | 4 |
| 2 | People and problems | 3 |
| 3 | Design and walkthrough (deep) | 8 |
| 4 | Live demo | 10 |
| 5 | Provenance deep-dive (deep) | 6 |
| 6 | Delegate / review / own | 2 |
| 7 | Quality and security (deep) | 3 |
| 8 | Non-engineers | 1 |
| 9 | Adoption | 2 |
| 10 | First 90 days | 1 |
| 11 | Build log and time spent | 1 |

## 1. Definition (4 min)

**A software factory is a contract, not a pipeline.** It is a shared protocol for how work moves between roles: planner, implementer, reviewer, human approver. Every hand-off is typed, stored in git, and chained into a verifiable ledger.

Where it sits on the range: near "how agents talk to each other", with one opinionated workflow on top. It is not at the "tasks in, production out" end.

What it is not:

- an autonomous pipeline that ships to production;
- a mandated tool: any runtime, or a human, can fill any role;
- a replacement for code review or CI. Merge and deploy go through the unchanged pipeline.

## 2. People and problems (3 min)

| Person | Problem | Now | Later | Never |
|---|---|---|---|---|
| Senior engineer | Agents break invariants | Protected paths, plan gate | Per-repo policy packs | Auto-merge |
| Early adopter | No proof that agents help | Cost and loop counts in the ledger | Metrics from the ledger | - |
| Team lead | Setups live in people's heads | Role prompts in the repo, hashed | Shared prompt library | Mandated tool |
| Platform engineer | What did the agent touch, at what cost? | Ledger: files, cost, tokens | Dashboard | - |
| Compliance / audit | Who approved this? | Ledger plus independent PR approval | Signed attestations | Agent as accountable author |
| Reviewer | Plausible but wrong code | Review map from `review-NNN.json`, blind first pass | - | Reviewer verdict replaces human |
| Non-engineer | Cannot use the process | Sketch only (section 8) | Template repos | Own deploys |

## 3. Design and walkthrough (8 min)

Components: protocol spec (`spec/`), the `factory` CLI, role prompts in `.factory/roles/`, a GitHub Action that re-runs verify, and a sample `orders/` module with protected invariant tests.

```
initiator -> planner -> plan_approval -> implementer (x N sessions) -> reviewer -> PR -> human approver
  human       agent        human              agent                    agent     CLI     human
             read-only                    edit + test            blind, read + test
```

Walkthrough, task T-001: "Allow cancelling the remaining quantity of a partially filled order."

| Step | Who | What | Ledger entry |
|---|---|---|---|
| `factory new` | human | Task folder, protected paths `tests/invariants/**` | initiator |
| `factory run planner` | agent, read-only | `plan.md` | planner |
| `factory approve-plan` | human | Approve or edit the plan | plan_approval |
| `factory run implementer` | agent | Code on `factory/T-001`, `handoff-001.json`; next session resumes from plan + hand-off | one per session |
| `factory run reviewer` | agent, fresh context | Sees task, plan, diff, test run; not the implementer's reasoning | reviewer |
| `factory pr` | CLI | Verify, then PR with a body generated from the ledger | - |
| CI | Action | Verify, tests, gitleaks | - |
| Approval | human, not initiator, not plan approver | Merge through the normal pipeline | GitHub review |

Where humans step in: starting the task, the plan gate (cheapest place to catch a plausible but wrong plan), manual changes, the PR approval, merge and deploy. If the reviewer rejects more than 3 times, the task needs a human.

## 4. Live demo (10 min)

The live run works: two rehearsals with Sonnet in scratch clones cost $0.59 and $0.28 for the whole task (planner, implementer, reviewer), took about 3 to 5 minutes, and ended `RESULT: PASS`. The PR is not opened yet. The fake runtime replays recorded role outputs and is the fallback. A screen capture of both is a separate manual step.

Script (full text in [demo/README.md](../demo/README.md)):

1. `factory new ... --id T-001`, `factory run planner`, read the plan, `factory approve-plan`.
2. `factory run implementer` twice (second session resumes from `handoff-001.json`).
3. `factory run reviewer`, `factory status`, `factory verify` -> PASS.
4. Tamper demo: append a line to `plan.md` after approval, commit, `factory verify` -> FAIL on "task files match the ledger (chain of custody)". Then `git reset --hard HEAD~1`.
5. PR (live only): `factory pr`. Before an independent human approves, the approval check fails. After a second person approves, it passes.

Fake dry run result: 6 ledger entries (initiator, planner, plan_approval, implementer x2, reviewer), `RESULT: PASS`.

## 5. Provenance deep-dive (6 min)

**Ledger entry.** One line in `ledger.jsonl`, written only by the CLI: seq, task, role, actor (kind, id, runtime, model), `on_behalf_of`, role-prompt hash, input and output file hashes, claimed commits, flat `cost_usd`/`tokens_in`/`tokens_out`, timestamps, `prev_hash`, `hash`. Schema: [ledger-entry.schema.json](../spec/ledger-entry.schema.json). Hash = sha256 of the canonical JSON without `hash`; the first `prev_hash` is 64 zeros.

**The authorship answer.**

- Accountable author: the human initiator. An agent is never accountable.
- Contributors: agents, with runtime, model and role-prompt hash.
- Approver: a different human, checked in CI.
- Audit question: who asked, with which prompt and model, what changed, who checked, who approved.

**Verify checks (9, plus approvals in CI).**

1. task folder is committed
2. base commit is an ancestor of HEAD
3. ledger hash chain intact
4. each role filled by the right kind of actor
5. task files match the ledger (chain of custody)
6. every code commit is claimed by exactly one entry
7. agents did not touch protected paths
8. roles ran in the required order
9. reviewer approved the final code
10. (CI, `--check-approvals`) independent human approval

**Honest limits** (full list: PROTOCOL.md section 8).

- Tamper-evident, not tamper-proof: write access lets someone rebuild the chain. Defences: agents cannot write `.factory/`, branch protection, CI recomputation.
- Model identity is self-reported; identity is `FACTORY_USER` or the `gh` login, unsigned.
- Reviewer blindness is prompt and tool policy, not a sandbox. Tool policies are permission rules; pytest arguments are unrestricted.
- Squash or rebase breaks commit claims. A failed ledger commit is not rolled back.
- A human may fill the implementer role, and the ledger then shows no agent wrote code. The plan approver may be the initiator.

**Roadmap.** One signed in-toto statement per ledger entry (sigstore / gitsign); verify checks signatures against an identity policy.

## 6. Delegate / review / own (2 min)

- **Delegate:** planning drafts, implementation, first-pass review.
- **Review:** the plan and the PR.
- **Own:** invariants, approval, merge and deploy, role prompts.

## 7. Quality and security (3 min)

- Blind reviewer: no implementer reasoning, no read access to the task folder (policy level).
- Tests are run by the factory, not trusted from the agent's report.
- Protected invariants: agents cannot edit `tests/invariants/**` or `.factory/**`; verify catches it if they do.
- gitleaks on every PR.
- Reviewer eval: 5 cases (1 control that should be approved, 4 seeded invariant bugs that should be rejected). Catch rate: **pending, not yet run** (the live run costs API credit; it waits for a decision).

## 8. Non-engineers (1 min)

Sketch only, not built. Same protocol plus an approved template repo. An engineer is the plan approver. It runs only inside the group's platform.

## 9. Adoption (2 min)

- Win the senior engineer by making the invariants theirs: protected paths plus the plan gate.
- Give the early adopter a measurable bar: ledger cost and loop counts.
- Give team leads shared role prompts in the repo.

## 10. First 90 days (1 min)

- Days 0-30: pilot with 2 volunteer teams, one per company.
- Days 30-60: signing, plus an MCP/IDE front-end.
- Days 60-90: non-engineer path, plus metrics from the ledger.

What I expect to learn: the value of the plan gate, the reviewer catch rate, cost per change.

## 11. Build log and time spent (1 min)

Source: [BUILD_LOG.md](../BUILD_LOG.md). Budget is about 4 h of human time; agent time and cost are in separate columns.

- Tasks 1-15 and 18 were built by Sonnet subagents; an Opus controller diffed each against the plan. Review subagents read the substantive tasks.
- Agent time per task: 0.5 to 7 min. The longest was verify (7 min, with adversarial review).
- Human time: many cells in the log are still "?". I do not have honest numbers for those yet, so I do not quote a total.
- What went wrong, from the reviews: the ledger split lines on Unicode separators; ledger commits swept in pre-staged files; a `claude.CMD` timeout hung; a `user.name` fallback weakened the approver rule; verify let approver `" alice"` and empty strings through. All fixed with tests (5 fix commits).
- Plan errors: a test used `run_reviewer` before it existed; a clone ran before fixtures were committed; the plan expected 7 ledger rows where 6 is correct.
- Live run (Task 16): two rehearsals, $0.88 in total. The first exposed blocked shell commands, so the role prompts were tuned (the prompt hash changes in the ledger).
- Not done yet: GitHub repo, PR and branch protection, live reviewer eval, screen capture.
