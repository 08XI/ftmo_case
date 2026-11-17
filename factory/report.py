"""Human-readable views of a task: status table and GitHub PR body; opening the PR."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from . import gitutil
from .core import TaskRef, latest_output, load_task, read_entries, verdict_reader
from .errors import FactoryError
from .schemas import Handoff, Review
from .verify import verify
from .workflow import allowed_next, describe_state


def status_text(ref: TaskRef) -> str:
    task = load_task(ref)
    entries = read_entries(ref)
    verdict_of = verdict_reader(ref)
    allowed = allowed_next(entries, verdict_of, task.max_review_loops)
    lines = [
        f"Task {task.id}: {task.title}",
        f"Branch: {task.branch}   Initiator: {task.initiator}",
        f"State: {describe_state(entries, verdict_of, task.max_review_loops)}   Next: {', '.join(sorted(allowed))}",
        f"Agent cost so far: ${sum(e.cost_usd for e in entries):.2f}",
        "",
        f"{'#':>3}  {'role':<14} {'actor':<28} {'model':<26} {'cost':>6}  commits",
    ]
    for e in entries:
        actor = f"{e.actor.kind}:{e.actor.id}"[:28]
        commits = ", ".join(c[:8] for c in e.commits) or "-"
        lines.append(f"{e.seq:>3}  {e.role:<14} {actor:<28} {(e.actor.model or '-')[:26]:<26} "
                     f"{e.cost_usd:>6.2f}  {commits}")
    last = latest_output(entries, "handoff-")
    if last:
        handoff = Handoff.model_validate_json(ref.path(last[0]).read_text(encoding="utf-8"))
        lines += ["", f"Last hand-off ({last[0]}): {handoff.status}, tests {handoff.tests}", f"  {handoff.summary}"]
        lines += [f"  remaining: {item}" for item in handoff.remaining]
    return "\n".join(lines)


def pr_body(ref: TaskRef) -> str:
    task = load_task(ref)
    entries = read_entries(ref)
    plan_approvers = sorted({e.actor.id for e in entries if e.role == "plan_approval"})
    rows = ["| # | Role | Actor | Model | Cost (USD) | Commits |", "|---|---|---|---|---|---|"]
    for e in entries:
        rows.append(f"| {e.seq} | {e.role} | {e.actor.kind}: `{e.actor.id}` | {e.actor.model or '-'} | "
                    f"{e.cost_usd:.2f} | {', '.join(c[:8] for c in e.commits) or '-'} |")
    lines = [
        f"## {task.id}: {task.title}", "", f"**Goal:** {task.goal}", "",
        "### Accountability", "",
        f"- **Accountable author (initiator):** `{task.initiator}`",
        f"- **Plan approved by:** {', '.join(f'`{a}`' for a in plan_approvers) or '-'}",
        "- **Merge approval:** must come from a human who is neither of the above. "
        "The `factory-verify` check enforces this.", "",
        "### Hand-off ledger", "", *rows, "",
        f"**Total agent cost:** ${sum(e.cost_usd for e in entries):.2f}", "",
    ]
    last_review = latest_output(entries, "review-")
    if last_review:
        review = Review.model_validate_json(ref.path(last_review[0]).read_text(encoding="utf-8"))
        lines += ["### Agent review (a map for the human reviewer, not a verdict)", "",
                  f"**{review.verdict}**: {review.summary}", ""]
        lines += [f"- [{f.severity}] `{f.file}`{':' + str(f.line) if f.line else ''} {f.message}"
                  for f in review.findings]
        lines += [f"- checked: {item}" for item in review.invariants_checked] + [""]
    lines += ["### Verify locally", "", "```bash", f"factory verify --task {task.id}", "```", "",
              f"Ledger: `{ref.rel('ledger.jsonl')}`. Plan: `{ref.rel('plan.md')}`.", ""]
    return "\n".join(lines)


def open_pr(ref: TaskRef, base: str = "main") -> str:
    report = verify(ref.repo, ref.task_id)
    if not report.ok:
        raise FactoryError("verify failed; fix it before opening a PR:\n" + report.render())
    task = load_task(ref)
    gitutil.git(ref.repo, "push", "-u", "origin", task.branch)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8", newline="\n") as fh:
        fh.write(pr_body(ref))
        body_path = Path(fh.name)
    try:
        proc = subprocess.run(["gh", "pr", "create", "--base", base, "--head", task.branch,
                               "--title", f"{task.id}: {task.title}", "--body-file", str(body_path)],
                              cwd=ref.repo, capture_output=True, text=True, encoding="utf-8")
    finally:
        body_path.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise FactoryError(f"gh pr create failed: {proc.stderr.strip()}")
    return proc.stdout.strip()
