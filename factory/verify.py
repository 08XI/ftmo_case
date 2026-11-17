"""factory verify: recompute the ledger and check it against git. Runs locally and in CI."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from . import gitutil, ledger
from .core import TaskRef, load_task, protected_violations, verdict_reader
from .errors import FactoryError, GitError
from .schemas import AGENT_ROLES, LedgerEntry, Task
from .workflow import VerdictOf, is_pr_ready, sequence_errors


@dataclass
class Check:
    name: str
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class Report:
    task_id: str
    checks: list[Check]

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def render(self) -> str:
        lines = [f"factory verify {self.task_id}"]
        for check in self.checks:
            lines.append(f"  [{'PASS' if check.ok else 'FAIL'}] {check.name}")
            lines += [f"         - {e}" for e in check.errors]
        lines.append("RESULT: " + ("PASS" if self.ok else "FAIL"))
        return "\n".join(lines)


def verify(repo: Path, task_id: str, approvers: list[str] | None = None) -> Report:
    repo = Path(repo)
    ref = TaskRef(repo, task_id)
    try:
        task = load_task(ref)
        entries = ledger.load(ref.dir)
        commits = gitutil.commits_between(repo, task.base_commit, "HEAD")
    except (FactoryError, ValidationError) as exc:
        return Report(task_id, [Check("task, ledger and base commit are readable", [str(exc)])])
    verdict_of = verdict_reader(ref)
    prefix = ref.rel("")
    code_commits = [c for c in commits if not _is_ledger_commit(repo, c, prefix)]
    checks = [
        Check("ledger hash chain intact", ledger.check_chain(entries)),
        Check("each role filled by the right kind of actor", _actor_errors(entries)),
        Check("task files match the ledger (chain of custody)", _custody_errors(ref, entries)),
        Check("every code commit is claimed by exactly one entry", _commit_errors(repo, entries, commits, prefix)),
        Check("agents did not touch protected paths", _protected_errors(repo, task, entries, commits)),
        Check("roles ran in the required order", sequence_errors(entries, verdict_of, task.max_review_loops)),
        Check("reviewer approved the final code", _review_errors(repo, entries, verdict_of, code_commits)),
    ]
    if approvers is not None:
        checks.append(Check("independent human approval", _approval_errors(task, entries, approvers)))
    return Report(task_id, checks)


def _is_ledger_commit(repo: Path, sha: str, prefix: str) -> bool:
    files = gitutil.files_in_commit(repo, sha)
    return bool(files) and all(f.startswith(prefix) for f in files) and len(gitutil.parents(repo, sha)) == 1


def _actor_errors(entries: list[LedgerEntry]) -> list[str]:
    errors = []
    for e in entries:
        needed = "agent" if e.role in AGENT_ROLES else "human"
        if e.actor.kind != needed:
            errors.append(f"entry {e.seq}: role '{e.role}' must be a {needed}, got {e.actor.kind}")
    return errors


def _custody_errors(ref: TaskRef, entries: list[LedgerEntry]) -> list[str]:
    errors = []
    latest: dict[str, str] = {}
    for e in entries:
        for name, digest in e.inputs.items():
            if name != "head" and latest.get(name) != digest:
                errors.append(f"entry {e.seq}: input {name} is not the last recorded version")
        latest.update(e.outputs)
    for name, digest in latest.items():
        path = ref.path(name)
        if not path.exists():
            errors.append(f"{name}: recorded in the ledger but missing")
        elif ledger.sha256_file(path) != digest:
            errors.append(f"{name}: changed outside the factory (hash mismatch)")
    for path in sorted(ref.dir.iterdir()):
        if path.name != ledger.LEDGER_FILE and path.name not in latest:
            errors.append(f"{path.name}: present in the task folder but not recorded in the ledger")
    return errors


def _commit_errors(repo: Path, entries: list[LedgerEntry], commits: list[str], prefix: str) -> list[str]:
    errors = []
    claimed: dict[str, int] = {}
    for e in entries:
        for sha in e.commits:
            if sha in claimed:
                errors.append(f"commit {sha[:8]} claimed by entries {claimed[sha]} and {e.seq}")
            claimed[sha] = e.seq
    for sha in commits:
        if len(gitutil.parents(repo, sha)) > 1:
            errors.append(f"{sha[:8]}: merge commit; keep the task branch linear")
            continue
        files = gitutil.files_in_commit(repo, sha)
        if files and all(f.startswith(prefix) for f in files):
            continue
        if any(f.startswith(".factory/") for f in files):
            errors.append(f"{sha[:8]}: code commit also changes .factory/")
        if sha not in claimed:
            errors.append(f"{sha[:8]}: not claimed by any ledger entry (record human edits with `factory record`)")
    on_branch = set(commits)
    errors += [f"entry {seq}: claims {sha[:8]}, which is not on this branch"
               for sha, seq in claimed.items() if sha not in on_branch]
    return errors


def _protected_errors(repo: Path, task: Task, entries: list[LedgerEntry], commits: list[str]) -> list[str]:
    patterns = [*task.protected_paths, ".factory/**"]
    on_branch = set(commits)
    errors = []
    for e in entries:
        if e.actor.kind != "agent":
            continue
        for sha in e.commits:
            if sha in on_branch:
                bad = protected_violations(gitutil.files_in_commit(repo, sha), patterns)
                if bad:
                    errors.append(f"entry {e.seq} ({e.role}) commit {sha[:8]} touched {', '.join(bad)}")
    return errors


def _review_errors(repo: Path, entries: list[LedgerEntry], verdict_of: VerdictOf,
                   code_commits: list[str]) -> list[str]:
    if not is_pr_ready(entries, verdict_of):
        return ["the last ledger entry must be a reviewer with verdict 'approved'"]
    reviewed = entries[-1].inputs.get("head", "")
    if not reviewed or not gitutil.is_ancestor(repo, reviewed):
        return [f"reviewed commit {reviewed[:8] or '?'} is not on this branch"]
    try:
        after = set(gitutil.commits_between(repo, reviewed, "HEAD"))
    except GitError as exc:
        return [str(exc)]
    late = [sha[:8] for sha in code_commits if sha in after]
    return [f"code changed after the review: {', '.join(late)}"] if late else []


def _approval_errors(task: Task, entries: list[LedgerEntry], approvers: list[str]) -> list[str]:
    # GitHub logins are case-insensitive, so compare casefolded on both sides.
    excluded = {task.initiator.casefold()} | {e.actor.id.casefold() for e in entries if e.role == "plan_approval"}
    if any(a.casefold() not in excluded for a in approvers):
        return []
    errors = [f"{a} cannot approve: initiator or plan approver" for a in approvers]
    return errors + ["needs approval from a human who is neither the initiator nor the plan approver"]
