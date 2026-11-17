"""The protocol's data contract. JSON Schemas in spec/ are generated from these models."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Role = Literal["initiator", "planner", "plan_approval", "implementer", "reviewer", "human_change"]
AGENT_ROLES: tuple[str, ...] = ("planner", "implementer", "reviewer")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Task(_Strict):
    id: str = Field(pattern=r"^T-[A-Za-z0-9-]+$")
    title: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    initiator: str = Field(min_length=1, description="Accountable human (GitHub login)")
    base_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    branch: str
    protected_paths: list[str] = Field(default_factory=lambda: ["tests/invariants/**"])
    test_command: list[str] = Field(default_factory=lambda: ["python", "-m", "pytest", "-q"])
    max_review_loops: int = Field(default=3, ge=1)
    created_at: str


class Plan(_Strict):
    summary: str = Field(min_length=1)
    steps: list[str] = Field(min_length=1)
    invariants_affected: list[str]
    test_plan: list[str] = Field(min_length=1)
    risks: list[str] = Field(default_factory=list)


class Handoff(_Strict):
    summary: str = Field(min_length=1)
    done: list[str]
    remaining: list[str]
    open_questions: list[str] = Field(default_factory=list)
    files_touched: list[str]
    tests: Literal["passing", "failing", "not_run"]
    status: Literal["complete", "in_progress", "blocked"]


class Finding(_Strict):
    severity: Literal["blocker", "major", "minor"]
    file: str
    line: int | None = None
    message: str = Field(min_length=1)


class Review(_Strict):
    verdict: Literal["approved", "changes_requested"]
    summary: str = Field(min_length=1)
    findings: list[Finding] = Field(default_factory=list)
    invariants_checked: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _approved_has_no_blockers(self) -> "Review":
        if self.verdict == "approved" and any(f.severity == "blocker" for f in self.findings):
            raise ValueError("an approved review cannot contain blocker findings")
        return self


class Actor(_Strict):
    kind: Literal["human", "agent"]
    id: str
    runtime: str | None = None
    model: str | None = None


class LedgerEntry(_Strict):
    seq: int = Field(ge=0)
    task: str
    role: Role
    actor: Actor
    on_behalf_of: str
    role_prompt_sha256: str | None = None
    inputs: dict[str, str] = Field(default_factory=dict, description="file name -> sha256; 'head' -> commit")
    outputs: dict[str, str] = Field(default_factory=dict, description="file name -> sha256")
    commits: list[str] = Field(default_factory=list)
    note: str | None = None
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    started_at: str
    ended_at: str
    prev_hash: str
    hash: str


SCHEMAS: dict[str, type[BaseModel]] = {
    "task": Task,
    "plan": Plan,
    "handoff": Handoff,
    "review": Review,
    "ledger-entry": LedgerEntry,
}


def export(out_dir: Path) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, model in SCHEMAS.items():
        path = out_dir / f"{name}.schema.json"
        path.write_text(json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n",
                        encoding="utf-8", newline="\n")
        written.append(path)
    return written


if __name__ == "__main__":
    for written_path in export(Path("spec")):
        print(written_path)
