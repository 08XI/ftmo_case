"""Which role may act next. Pure functions over ledger entries; no IO."""
from __future__ import annotations

from typing import Callable

from .errors import WorkflowError
from .schemas import LedgerEntry

VerdictOf = Callable[[LedgerEntry], "str | None"]
CODE_ROLES = {"implementer", "human_change"}


def _rejections(entries: list[LedgerEntry], verdict_of: VerdictOf) -> int:
    return sum(1 for e in entries if e.role == "reviewer" and verdict_of(e) == "changes_requested")


def allowed_next(entries: list[LedgerEntry], verdict_of: VerdictOf, max_review_loops: int) -> set[str]:
    if not entries:
        return {"initiator"}
    last = entries[-1].role
    if last == "initiator":
        return {"planner"}
    if last == "planner":
        return {"planner", "plan_approval"}
    if last == "plan_approval":
        return {"implementer", "human_change"}
    if last in CODE_ROLES:
        return {"implementer", "human_change", "reviewer"}
    if last == "reviewer":
        if verdict_of(entries[-1]) != "approved" and _rejections(entries, verdict_of) >= max_review_loops:
            return {"human_change"}
        return {"implementer", "human_change"}
    raise WorkflowError(f"unknown role {last!r}")


def sequence_errors(entries: list[LedgerEntry], verdict_of: VerdictOf, max_review_loops: int) -> list[str]:
    errors = []
    for index, entry in enumerate(entries):
        allowed = allowed_next(entries[:index], verdict_of, max_review_loops)
        if entry.role not in allowed:
            errors.append(f"entry {entry.seq}: '{entry.role}' not allowed here (expected {', '.join(sorted(allowed))})")
    return errors


def is_pr_ready(entries: list[LedgerEntry], verdict_of: VerdictOf) -> bool:
    return bool(entries) and entries[-1].role == "reviewer" and verdict_of(entries[-1]) == "approved"


def describe_state(entries: list[LedgerEntry], verdict_of: VerdictOf, max_review_loops: int) -> str:
    if not entries:
        return "empty"
    last = entries[-1].role
    if last == "initiator":
        return "needs a plan"
    if last == "planner":
        return "plan awaiting human approval"
    if last == "plan_approval":
        return "ready for implementation"
    if last in CODE_ROLES:
        return "implementation in progress"
    if verdict_of(entries[-1]) == "approved":
        return "approved by reviewer - ready for PR"
    if allowed_next(entries, verdict_of, max_review_loops) == {"human_change"}:
        return "needs a human (review loop limit reached)"
    return "changes requested by reviewer"
