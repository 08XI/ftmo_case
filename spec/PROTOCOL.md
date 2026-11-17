# Hand-off protocol

Version 0.1. This is the contract. `factory/` is one implementation of it; any tool or person that follows these rules can fill a role. The JSON Schemas in this folder are generated from `factory/schemas.py`. Rationale and decisions are in the [design doc](../docs/plans/2026-11-16-handoff-protocol-design.md).

## 1. Roles

| Role | Kind | What it does |
|---|---|---|
| `initiator` | human | Creates the task. The accountable author. |
| `planner` | agent | Writes `plan.md` with read-only tools. |
| `plan_approval` | human | Approves or edits the plan. |
| `implementer` | agent | Writes code in sessions; writes one hand-off per session. |
| `reviewer` | agent | Blind review of the diff; writes `review-NNN.json`. |
| `human_change` | human | A manual code change (`factory record`). |

Agent roles: planner, implementer, reviewer. Human roles: initiator, plan_approval, human_change. Verify rejects an entry whose actor kind does not match the role. A human may do any agent's job, but must record it as `human_change`.

## 2. Task folder

`.factory/tasks/<task-id>/` on the branch `factory/<task-id>`.

| File | Written by | Schema |
|---|---|---|
| `task.json` | CLI, at `factory new` | [task.schema.json](task.schema.json) |
| `plan.md` | planner (front-matter is validated) | [plan.schema.json](plan.schema.json) |
| `handoff-NNN.json` | implementer session NNN | [handoff.schema.json](handoff.schema.json) |
| `review-NNN.json` | reviewer run NNN | [review.schema.json](review.schema.json) |
| `ledger.jsonl` | CLI only, append-only | [ledger-entry.schema.json](ledger-entry.schema.json) |

Only the CLI writes into this folder. Role prompts live in `.factory/roles/*.md`.

## 3. Ledger

One JSON object per line, canonical form, `\n` line endings. Fields (see the schema for types):

| Field | Meaning |
|---|---|
| `seq` | Position, from 0. |
| `task`, `role` | Task id and role. |
| `actor` | `kind` (`human`/`agent`), `id`, and for agents `runtime` and `model`. |
| `on_behalf_of` | The initiator. |
| `role_prompt_sha256` | Hash of the role prompt used (agents only). |
| `inputs`, `outputs` | File name to sha256. `inputs.head` is a commit (for the reviewer: the reviewed head). |
| `commits` | Code commits this entry claims. |
| `note` | Free text (used for human changes). |
| `cost_usd`, `tokens_in`, `tokens_out` | Flat fields, as reported by the runtime. |
| `started_at`, `ended_at` | Timestamps. |
| `prev_hash`, `hash` | The chain. |

Hash rule: `hash = sha256(canonical JSON of the entry without "hash")`. Canonical JSON means sorted keys, separators `(",", ":")`, `ensure_ascii=False`, UTF-8. `prev_hash` of entry 0 is 64 zeros; every other entry carries the `hash` of the one before.

## 4. Commit rules

- A code commit is claimed by exactly one ledger entry (in `commits`).
- A ledger commit touches only the task folder. A code commit never touches `.factory/`.
- Task branches are linear: no merge commits. Do not rebase, amend or merge `main` into the branch after the ledger is written.
- Trailers on factory commits: `Factory-Task`, `Factory-Entry`, `Factory-Role`.
- Agent code commits also carry `Co-authored-by: <runtime> (<model>) <agent@factory.invalid>`.
- An unclaimed commit fails verify. Record a human edit with `factory record -m "..."`.

## 5. Role order

`allowed_next` (from `factory/workflow.py`):

| Last role | Allowed next |
|---|---|
| (empty) | `initiator` |
| `initiator` | `planner` |
| `planner` | `planner`, `plan_approval` |
| `plan_approval` | `implementer`, `human_change` |
| `implementer` or `human_change` | `implementer`, `human_change`, `reviewer` |
| `reviewer` | `implementer`, `human_change` |
| `reviewer`, not approved, rejections >= `max_review_loops` (default 3) | `human_change` only |

A PR is ready when the last entry is a reviewer with verdict `approved`.

## 6. `factory verify`

Nine checks, run on the task branch:

1. task folder is committed
2. base commit is an ancestor of HEAD
3. ledger hash chain intact
4. each role filled by the right kind of actor
5. task files match the ledger (chain of custody)
6. every code commit is claimed by exactly one entry
7. agents did not touch protected paths
8. roles ran in the required order
9. reviewer approved the final code (the reviewed `head` is on the branch and no code commit came after it)

With `--check-approvals --approver <login>` (CI) there is a tenth check, **independent human approval**. At least one approver must be neither the initiator nor a plan approver. Logins are trimmed, a leading `@` is dropped, and comparison is case-insensitive.

Protected paths are the task's `protected_paths` (default `tests/invariants/**`) plus `.factory/**`.

## 7. Authorship

- The **initiator** is the accountable author. An agent is never accountable.
- **Agents** are contributors, recorded with runtime, model and role-prompt hash.
- The **approver** is a different human, checked in CI against the latest GitHub review per user.
- Identity is `FACTORY_USER`, else the `gh` login. There is no fallback to git `user.name`, because a display name never matches a reviewer login.
- The ledger answers: who asked, with which prompt and model, what changed, who checked it, who approved it.

Tool policies (`factory/prompts.py`):

| Role | Allowed | Denied |
|---|---|---|
| planner | Read, Grep, Glob | Edit, Write, Bash |
| implementer | Read, Grep, Glob, Edit, Write, `Bash(python -m pytest:*)` | Edit/Write on protected paths |
| reviewer | Read, Grep, Glob, `Bash(python -m pytest:*)` | Edit, Write, `Read(.factory/tasks/**)` |

## 8. Limits

The ledger is tamper-evident, not tamper-proof. Someone with write access can rebuild the whole chain. Defences: agents cannot write `.factory/`, branch protection, and CI recomputation.

- Identity is `FACTORY_USER` or the `gh` login, and it is unsigned.
- Model identity is self-reported by the runtime.
- Reviewer independence relies on the prompt and the tool policy. The reviewer does not get the implementer's reasoning, but this is not a sandbox.
- Tool policies are permission rules, not a sandbox: pytest arguments are unrestricted, so a role can run code through pytest.
- Squash or rebase invalidates commit claims. Merge with a merge commit on `main`, or verify before squashing.
- If a ledger commit fails after the append, nothing is rolled back. A failed implementer ledger commit leaves an unclaimed code commit.
- Task-folder-only commits are not replayed against history. A file added and deleted between ledger writes leaves no trace, and a rebuilt chain is not detected by verify alone.
- Protected-path patterns are case-sensitive.
- Role-prompt hashes are recorded, not re-verified. The prompts at the base commit are trusted.
- A human may fill the implementer role (`human_change`). The ledger then shows that no agent wrote the code.
- The plan approver may be the initiator. Only the PR approver must be someone else.
- The review loop limit is soft: a `human_change` re-opens the implementer.
- The schema drift test pins the output of the installed pydantic. CI installs the latest pydantic and may need a pin.
- CI reads PR reviews page by page; the "latest review per user" grouping is applied per page.
- `LedgerEntry` constrains values loosely (hash format, negative cost, key names). The chain and verify catch the effects.
- No lock: one writer at a time.

## 9. Roadmap

Map each ledger entry 1:1 to a signed in-toto statement (sigstore / gitsign). Verify then checks signatures against an identity policy, which removes the self-reported identity limit.
