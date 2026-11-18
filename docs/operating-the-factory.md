# Operating the factory

A runbook for an agent or person who runs a task through the factory from start to pull request. The contract is in [spec/PROTOCOL.md](../spec/PROTOCOL.md). This page covers the practice.

## Before you start

- Python 3.11+, git, and the package installed (`pip install -e ".[dev]"`). Activate the virtual environment so `factory` is on your `PATH`, or use `python -m factory`.
- Start from a clean working tree on `main`. `factory new` refuses to run with uncommitted changes.
- Identity: set `FACTORY_USER` to the GitHub login of the accountable human. Without it the CLI asks `gh api user`. It never uses the git `user.name`.
- Runtime: `FACTORY_RUNTIME=claude` (default, needs `claude` on `PATH`) or `fake` with `FACTORY_FAKE_DIR=demo/fake` for offline runs. `FACTORY_MODEL` picks a model alias for the Claude runtime.
- Use the fake runtime to learn the flow or to test changes to the CLI. Use the live runtime only when a human asked for real agents, because it costs money.

## Lifecycle

| Step | Command | Result | Next allowed |
|---|---|---|---|
| 1 | `factory new "<title>" --goal "<what done looks like>" --id T-001` | Branch `factory/T-001`, `task.json`, initiator entry | planner |
| 2 | `factory run planner` | `plan.md`, read-only agent | planner (retry), plan approval |
| 3 | Read `plan.md`. Edit it if needed. `factory approve-plan` | Human gate. An edit is recorded in the ledger | implementer, human change |
| 4 | `factory run implementer` | Code commit and `handoff-NNN.json`. Repeat while the status is `in_progress` | implementer, human change, reviewer |
| 5 | `factory run reviewer` | Runs the test suite, then a blind review: `review-NNN.json` | implementer or human change if changes were requested |
| 6 | `factory status`, then `factory verify` | State, cost, and the nine checks | |
| 7 | `factory pr` | Verifies, pushes, opens a PR with the provenance body | |

`factory status` always prints the current state and the allowed next roles. When unsure, run it.

Steps 3 and 7 and the PR approval are human decisions. If you are an agent operating the factory, stop at the human gates and ask.

## Good practice

- One task per branch. Do not stack tasks.
- Keep the task goal specific and testable. The planner is told not to guess on ambiguous goals.
- Read `plan.md` before approving. This is the only point where a human can cheaply redirect the work.
- Never edit `.factory/` by hand. Verify flags any file that changed outside the CLI. The one exception is `plan.md` between `factory run planner` and `factory approve-plan`.
- Record your own code edits with `factory record -m "what and why"`. An unrecorded commit fails verify. After a human change the reviewer must run again.
- Do not rebase, amend, squash or merge `main` into the task branch after the ledger exists. Merge the PR with a merge commit, or run `factory verify` before squashing.
- Run `factory verify` before every push. CI runs it again on `factory/*` pull requests.
- The reviewer approval is only a map for the human reviewer. The reviewer is not independent of the prompt and tool policy, and tool policies are not a sandbox.

## When something fails

| Symptom | Cause | Fix |
|---|---|---|
| `working tree has uncommitted changes` | A command needs a clean tree | Commit, stash or restore your changes |
| `cannot do '<role>' now; allowed next: ...` | The role order forbids it | Run `factory status` and use an allowed role |
| `implementer changed protected paths ... Nothing recorded` | The agent edited `tests/invariants/` or `.factory/` | Inspect with `git status`, restore those paths, run the implementer again |
| `<role> output rejected; no ledger entry written` | The agent's final JSON block was invalid | Run the role again. Nothing was recorded |
| `reviewer must not modify files` | The reviewer changed files | Restore them and run the reviewer again |
| Verify: `not claimed by any ledger entry` | A code commit has no ledger entry | Do not commit by hand. Leave human edits uncommitted and run `factory record`. A stray commit that already exists needs a human to resolve it |
| Verify: `code changed after the review` | Code changed after the reviewed commit | Run the reviewer again |
| Verify: `changed outside the factory (hash mismatch)` | A task file was edited by hand | Restore the file from git (`git checkout -- <file>`) |
| After 3 rejected reviews only a human change is allowed | `max_review_loops` reached | A human edits the code and runs `factory record`, then the reviewer runs again |
| `'claude' not found on PATH` | The Claude Code CLI is not installed or not on `PATH` | Install it, or use `FACTORY_RUNTIME=fake` |
| `cannot resolve your identity` | No `FACTORY_USER` and no `gh` login | Set `FACTORY_USER` |

## Platform notes

- Windows: use Git Bash or PowerShell. The native Claude Code installer puts `claude` in `~/.local/bin`. Role tool policies allow `python -m pytest` through both the Bash and PowerShell tools.
- Role agents may run only `python -m pytest`. They cannot `cd` or chain commands.
- The reviewer step runs the whole test suite, about 80 seconds here.
- Plan files with CRLF line endings are normalised to LF at approval, because ledger hashes depend on exact bytes.

## Demo and tamper test

A scripted run with recorded outputs, plus a tamper demonstration, is in [demo/README.md](../demo/README.md).
