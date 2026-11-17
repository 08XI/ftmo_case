"""Factory operations: each one validates, records one ledger entry, and commits."""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, ValidationError

from . import gitutil, ledger
from .errors import AgentOutputError, FactoryError, ProtectedPathError, WorkflowError
from .prompts import build_prompt, policy_for, role_prompt_path
from .runtime import RunResult, Runtime, extract_json_block
from .schemas import Actor, Finding, Handoff, LedgerEntry, Plan, Review, Task
from .workflow import allowed_next

TASKS_DIR = Path(".factory") / "tasks"
FACTORY_PREFIX = ".factory/"
TestRunner = Callable[[Path], "tuple[bool, str]"]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class TaskRef:
    repo: Path
    task_id: str

    @property
    def dir(self) -> Path:
        return Path(self.repo) / TASKS_DIR / self.task_id

    def path(self, name: str) -> Path:
        return self.dir / name

    def rel(self, name: str) -> str:
        return f".factory/tasks/{self.task_id}/{name}"


# ---------- reading state ----------

def resolve_user(repo: Path) -> str:
    """Who is acting: FACTORY_USER, else the gh login, else git user.name."""
    if os.environ.get("FACTORY_USER"):
        return os.environ["FACTORY_USER"]
    try:
        proc = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True, timeout=15)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    name = gitutil.config(repo, "user.name")
    if name:
        return name
    raise FactoryError("cannot resolve your identity; set FACTORY_USER to your GitHub login")


def load_task(ref: TaskRef) -> Task:
    path = ref.path("task.json")
    if not path.exists():
        raise FactoryError(f"task {ref.task_id} not found at {path}")
    return Task.model_validate_json(path.read_text(encoding="utf-8"))


def read_entries(ref: TaskRef) -> list[LedgerEntry]:
    return ledger.load(ref.dir)


def latest_output(entries: list[LedgerEntry], prefix: str) -> tuple[str, str] | None:
    """Most recent (file name, sha256) output whose name starts with prefix."""
    for entry in reversed(entries):
        for name, digest in sorted(entry.outputs.items(), reverse=True):
            if name.startswith(prefix):
                return name, digest
    return None


def verdict_reader(ref: TaskRef) -> Callable[[LedgerEntry], str | None]:
    def verdict_of(entry: LedgerEntry) -> str | None:
        name = next((n for n in entry.outputs if n.startswith("review-")), None)
        if name is None:
            return None
        try:
            return Review.model_validate_json(ref.path(name).read_text(encoding="utf-8")).verdict
        except (OSError, ValidationError):
            return None
    return verdict_of


def protected_violations(paths: list[str], patterns: list[str]) -> list[str]:
    return sorted(p for p in paths if any(fnmatchcase(p, pattern) for pattern in patterns))


# ---------- internals ----------

def _require(ref: TaskRef, role: str) -> tuple[Task, list[LedgerEntry]]:
    task = load_task(ref)
    entries = read_entries(ref)
    allowed = allowed_next(entries, verdict_reader(ref), task.max_review_loops)
    if role not in allowed:
        raise WorkflowError(f"cannot do '{role}' now; allowed next: {', '.join(sorted(allowed)) or 'nothing'}")
    return task, entries


def _require_clean(repo: Path, allow: tuple[str, ...] = ()) -> None:
    dirty = [p for p in gitutil.changed_paths(repo) if p not in allow]
    if dirty:
        raise FactoryError(f"working tree has uncommitted changes: {', '.join(dirty[:10])}")


def _reject_changes(ref: TaskRef, role: str) -> None:
    changed = gitutil.changed_paths(ref.repo)
    if changed:
        raise ProtectedPathError(f"{role} must not modify files but changed: {', '.join(changed)}; nothing recorded")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def _write_model(path: Path, model: BaseModel) -> None:
    _write_text(path, model.model_dump_json(indent=2) + "\n")


def _read(ref: TaskRef, name: str) -> str:
    return ref.path(name).read_text(encoding="utf-8")


def _hash_of(ref: TaskRef, *names: str) -> dict[str, str]:
    return {name: ledger.sha256_file(ref.path(name)) for name in names}


def _trailers(ref: TaskRef, seq: int, role: str) -> str:
    return f"Factory-Task: {ref.task_id}\nFactory-Entry: {seq}\nFactory-Role: {role}\n"


def _commit_ledger(ref: TaskRef, entry: LedgerEntry, names: list[str]) -> str:
    paths = [ref.rel(n) for n in names] + [ref.rel(ledger.LEDGER_FILE)]
    message = f"{ref.task_id}: ledger #{entry.seq} {entry.role}\n\n" + _trailers(ref, entry.seq, entry.role)
    return gitutil.commit_paths(ref.repo, paths, message)


def _human(user: str) -> Actor:
    return Actor(kind="human", id=user)


def _call_agent(ref: TaskRef, task: Task, entries: list[LedgerEntry], role: str, runtime: Runtime,
                sections: list[tuple[str, str]], output_model: type[BaseModel]):
    role_file = role_prompt_path(ref.repo, role)
    if not role_file.exists():
        raise FactoryError(f"missing role prompt {role_file}")
    prompt = build_prompt(role_file.read_text(encoding="utf-8"), sections, output_model)
    attempt = sum(1 for e in entries if e.role == role)
    started = utc_now()
    result = runtime.run(role=role, prompt=prompt, policy=policy_for(role, task), cwd=Path(ref.repo), attempt=attempt)
    try:
        payload = output_model.model_validate(extract_json_block(result.text))
    except (AgentOutputError, ValidationError) as exc:
        raise AgentOutputError(f"{role} output rejected; no ledger entry written.\n{exc}") from exc
    return payload, result, ledger.sha256_file(role_file), started


def _agent_fields(ref: TaskRef, task: Task, role: str, result: RunResult, role_sha: str, started: str, *,
                  inputs: dict[str, str], outputs: dict[str, str], commits: list[str], note: str | None = None):
    notes = [n for n in (note, f"tool denials: {', '.join(result.denials)}" if result.denials else None) if n]
    return dict(
        task=ref.task_id, role=role,
        actor=Actor(kind="agent", id=f"{result.runtime}/{role}", runtime=result.runtime, model=result.model),
        on_behalf_of=task.initiator, role_prompt_sha256=role_sha, inputs=inputs, outputs=outputs,
        commits=commits, note="; ".join(notes) or None, cost_usd=result.cost_usd,
        tokens_in=result.tokens_in, tokens_out=result.tokens_out, started_at=started, ended_at=utc_now(),
    )


def render_plan(task: Task, plan: Plan) -> str:
    lines = [f"# Plan for {task.id}: {task.title}", "", plan.summary, "", "## Steps", ""]
    lines += [f"{i}. {step}" for i, step in enumerate(plan.steps, start=1)]
    lines += ["", "## Invariants affected", ""]
    lines += [f"- {item}" for item in plan.invariants_affected] or ["- none"]
    lines += ["", "## Test plan", ""] + [f"- {item}" for item in plan.test_plan]
    if plan.risks:
        lines += ["", "## Risks", ""] + [f"- {item}" for item in plan.risks]
    return "\n".join(lines) + "\n"


# ---------- operations ----------

def new_task(repo: Path, title: str, goal: str, task_id: str | None = None,
             protected_paths: list[str] | None = None, user: str | None = None) -> TaskRef:
    repo = Path(repo)
    _require_clean(repo)
    task_id = task_id or f"T-{secrets.token_hex(3)}"
    ref = TaskRef(repo, task_id)
    if ref.dir.exists():
        raise FactoryError(f"task {task_id} already exists")
    user = user or resolve_user(repo)
    base = gitutil.head(repo)
    branch = f"factory/{task_id}"
    gitutil.git(repo, "checkout", "-q", "-b", branch)
    ref.dir.mkdir(parents=True)
    task = Task(id=task_id, title=title, goal=goal, initiator=user, base_commit=base, branch=branch,
                protected_paths=protected_paths or ["tests/invariants/**"], created_at=utc_now())
    _write_model(ref.path("task.json"), task)
    now = utc_now()
    entry = ledger.append(ref.dir, task=task_id, role="initiator", actor=_human(user), on_behalf_of=user,
                          outputs=_hash_of(ref, "task.json"), started_at=now, ended_at=now)
    _commit_ledger(ref, entry, ["task.json"])
    return ref


def run_planner(ref: TaskRef, runtime: Runtime) -> LedgerEntry:
    task, entries = _require(ref, "planner")
    _require_clean(ref.repo)
    head = gitutil.head(ref.repo)
    sections = [("Task", _read(ref, "task.json"))]
    plan, result, role_sha, started = _call_agent(ref, task, entries, "planner", runtime, sections, Plan)
    _reject_changes(ref, "planner")
    _write_text(ref.path("plan.md"), render_plan(task, plan))
    entry = ledger.append(ref.dir, **_agent_fields(
        ref, task, "planner", result, role_sha, started,
        inputs={**_hash_of(ref, "task.json"), "head": head}, outputs=_hash_of(ref, "plan.md"), commits=[]))
    _commit_ledger(ref, entry, ["plan.md"])
    return entry


def approve_plan(ref: TaskRef, user: str | None = None, note: str | None = None) -> LedgerEntry:
    task, entries = _require(ref, "plan_approval")
    _require_clean(ref.repo, allow=(ref.rel("plan.md"),))
    user = user or resolve_user(ref.repo)
    recorded = latest_output(entries, "plan.md")[1]
    current = ledger.sha256_file(ref.path("plan.md"))
    notes = [n for n in ("approver edited the plan" if current != recorded else None, note) if n]
    now = utc_now()
    entry = ledger.append(ref.dir, task=ref.task_id, role="plan_approval", actor=_human(user),
                          on_behalf_of=task.initiator, inputs={"plan.md": recorded},
                          outputs={"plan.md": current}, note="; ".join(notes) or None,
                          started_at=now, ended_at=now)
    _commit_ledger(ref, entry, ["plan.md"])
    return entry


def _last_reviewer_requested_changes(ref: TaskRef, entries: list[LedgerEntry]) -> str | None:
    """Name of the latest review file if it requested changes and no implementer ran since."""
    for entry in reversed(entries):
        if entry.role == "implementer":
            return None
        if entry.role == "reviewer":
            if verdict_reader(ref)(entry) == "changes_requested":
                return next(n for n in entry.outputs if n.startswith("review-"))
            return None
    return None


def run_implementer(ref: TaskRef, runtime: Runtime) -> LedgerEntry:
    task, entries = _require(ref, "implementer")
    leftover = gitutil.changed_paths(ref.repo)
    if any(p.startswith(FACTORY_PREFIX) for p in leftover):
        raise FactoryError("uncommitted changes under .factory/; restore them before running an agent")
    head_before = gitutil.head(ref.repo)
    inputs = {**_hash_of(ref, "task.json", "plan.md"), "head": head_before}
    sections = [("Task", _read(ref, "task.json")), ("Approved plan", _read(ref, "plan.md"))]
    last_handoff = latest_output(entries, "handoff-")
    if last_handoff:
        inputs.update(_hash_of(ref, last_handoff[0]))
        sections.append(("Previous hand-off - resume from here", _read(ref, last_handoff[0])))
    review_name = _last_reviewer_requested_changes(ref, entries)
    if review_name:
        inputs.update(_hash_of(ref, review_name))
        sections.append(("Reviewer findings to address", _read(ref, review_name)))
    if leftover:
        sections.append(("Uncommitted work from an interrupted session",
                         f"Files: {', '.join(leftover)}\n\n```diff\n{gitutil.working_diff(ref.repo)}\n```"))

    handoff, result, role_sha, started = _call_agent(ref, task, entries, "implementer", runtime, sections, Handoff)

    changed = gitutil.changed_paths(ref.repo)
    bad = protected_violations(changed, [*task.protected_paths, ".factory/**"])
    if bad:
        raise ProtectedPathError(f"implementer changed protected paths: {', '.join(bad)}. Nothing recorded; "
                                 "inspect with `git status` and restore them.")
    seq = len(entries)
    session = sum(1 for e in entries if e.role == "implementer") + 1
    commits = []
    if changed:
        message = (f"{ref.task_id}: implementer session {session}\n\n" + _trailers(ref, seq, "implementer")
                   + f"Co-authored-by: {result.runtime} ({result.model}) <agent@factory.invalid>\n")
        commits.append(gitutil.commit_all_except_factory(ref.repo, message))
    name = f"handoff-{session:03d}.json"
    _write_model(ref.path(name), handoff)
    entry = ledger.append(ref.dir, **_agent_fields(ref, task, "implementer", result, role_sha, started,
                                                   inputs=inputs, outputs=_hash_of(ref, name), commits=commits))
    _commit_ledger(ref, entry, [name])
    return entry


def record_human(ref: TaskRef, message: str, user: str | None = None) -> LedgerEntry:
    task, entries = _require(ref, "human_change")
    changed = gitutil.changed_paths(ref.repo)
    if any(p.startswith(FACTORY_PREFIX) for p in changed):
        raise FactoryError("changes under .factory/ cannot be recorded; only the CLI writes there")
    if not changed:
        raise FactoryError("nothing to record: no uncommitted changes")
    user = user or resolve_user(ref.repo)
    started = utc_now()
    head_before = gitutil.head(ref.repo)
    sha = gitutil.commit_all_except_factory(
        ref.repo, f"{ref.task_id}: {message}\n\n" + _trailers(ref, len(entries), "human_change"))
    entry = ledger.append(ref.dir, task=ref.task_id, role="human_change", actor=_human(user), on_behalf_of=user,
                          inputs={"head": head_before}, commits=[sha], note=message,
                          started_at=started, ended_at=utc_now())
    _commit_ledger(ref, entry, [])
    return entry
