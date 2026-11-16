# Hand-off Protocol with Provenance — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build `factory`, a Python CLI that moves one change through planner → human plan gate → implementer session(s) → blind reviewer → GitHub PR. Every hand-off is a schema-validated file recorded in a hash-chained ledger, and `factory verify` checks the result locally and in CI.

**Architecture:** Agents never write `.factory/`. Each role runs headless (`claude -p`, or a deterministic `fake` runtime) and ends with a JSON block. The CLI validates that block with pydantic, writes the hand-off file, appends a ledger entry (sha256 chain) and commits. Code commits and ledger commits are kept separate, so `verify` can require that every code commit is claimed by exactly one ledger entry. A GitHub Action re-runs `verify` with the PR's approvals.

**Tech Stack:** Python 3.12, typer, pydantic v2, pytest, hypothesis, git, GitHub CLI (`gh`), Claude Code CLI 2.x, GitHub Actions, gitleaks.

**Design doc:** `docs/plans/2026-11-16-handoff-protocol-design.md`

---

## Conventions for the executor

- Work from the repo root `C:\Users\miro8\case` in Git Bash.
- Python: `.venv/Scripts/python` (Windows venv). In commands below, `PY=.venv/Scripts/python`.
- All text files are LF. `.gitattributes` enforces this, because ledger hashes depend on exact bytes. When writing files from Python, always pass `encoding="utf-8", newline="\n"`.
- Commit after every task. Every commit message ends with:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
- Log time and notable events in `BUILD_LOG.md` at the end of each task. Record what was delegated, what was reviewed, what was hand-written and what went wrong.
- Known environment facts (checked 2026-11-16):
  - Python 3.12.10, `gh` 2.88.1 and `claude` 2.1.316 are installed. `uv` is not installed.
  - Global `core.autocrlf=true`, which is why `.gitattributes` is needed.
  - `claude -p --output-format json` returns `{type:"result", subtype, is_error, result, total_cost_usd, usage{input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens}, modelUsage{<model>:{costUSD,…}}, permission_denials[], session_id}`.
  - **On failure it can return `is_error: true` with `subtype: "success"`**, so always check `is_error`.
  - Flags confirmed to exist: `--setting-sources`, `--strict-mcp-config`, `--no-session-persistence`, `--allowedTools <tools...>`, `--disallowedTools <tools...>`, `--permission-mode`, `--model`.
  - The local `claude` CLI OAuth session had expired at the time of the check. Re-login before Task 16.

---

### Task 1: Repository scaffold

**Files:**
- Create: `.gitattributes`, `.gitignore`, `pyproject.toml`, `factory/__init__.py`, `factory/__main__.py` (temporary stub), `orders/__init__.py`, `tests/__init__.py`, `tests/factory/__init__.py`, `tests/orders/__init__.py`, `tests/invariants/__init__.py`, `AGENTS.md`, `CLAUDE.md`, `BUILD_LOG.md`

**Step 1: Write `.gitattributes`**

```
* text=auto eol=lf
*.png binary
```

**Step 2: Write `.gitignore`**

```
.venv/
__pycache__/
*.egg-info/
.pytest_cache/
.hypothesis/
evals/results/*.tmp
```

**Step 3: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "software-factory"
version = "0.1.0"
description = "Hand-off protocol with provenance for agent-built changes"
requires-python = ">=3.11"
dependencies = ["typer>=0.12", "pydantic>=2.6"]

[project.optional-dependencies]
dev = ["pytest>=8", "hypothesis>=6.100"]

[project.scripts]
factory = "factory.cli:app"

[tool.setuptools.packages.find]
include = ["factory*", "orders*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

**Step 4: Package stubs**

`factory/__init__.py`:
```python
"""Software factory: typed, ledgered hand-offs between agent and human roles."""

__version__ = "0.1.0"
```

`orders/__init__.py`, `tests/__init__.py`, `tests/factory/__init__.py`, `tests/orders/__init__.py` and `tests/invariants/__init__.py` are all empty files.

**Step 5: Write `AGENTS.md`**

```markdown
# AGENTS.md

Instructions for any coding agent (Claude Code, Codex, Cursor) in this repository,
whether you are building the factory or playing a factory role (planner, implementer, reviewer).

## What is here
- `factory/`: the `factory` CLI, a hand-off protocol with a hash-chained ledger. Contract: `spec/PROTOCOL.md`.
- `orders/`: a synthetic order-handling module that factory agents work on. Not real trading code.
- `spec/*.schema.json`: generated from `factory/schemas.py` by `python -m factory.schemas`. Never edit by hand.
- `.factory/roles/`: role prompts. They are hashed into every ledger entry; changing them changes agent behaviour.
- `.factory/tasks/`: task folders. Only the `factory` CLI writes here.

## Commands
- Install: `python -m venv .venv` then `.venv/Scripts/python -m pip install -e ".[dev]"` (Windows) or `.venv/bin/python ...` (Linux/macOS).
- Test: `python -m pytest -q`
- Regenerate schemas: `python -m factory.schemas`

## Rules
- Never edit `tests/invariants/`. Humans own the invariants.
- Never edit `.factory/tasks/` by hand.
- Files are LF (`.gitattributes`). Ledger hashes depend on exact bytes.
- Test first: write the failing test, see it fail, then implement.
- Python 3.11+, type hints, no new dependencies without a reason.
```

**Step 6: Write `CLAUDE.md`**

```markdown
@AGENTS.md
```

**Step 7: Write `BUILD_LOG.md`**

```markdown
# Build log

Time budget: ~4 h total (design, prototype, presentation). Times are wall-clock.

| When | Step | Time | Delegated to agent | Reviewed by me | Written by hand | What went wrong |
|---|---|---|---|---|---|---|
| 2026-11-16 19:22 | Brainstorm + design doc | 10 min | Options, drafts of each design section | Every section, approved one by one | Choices: hand-off protocol, files in repo, claude -p, Python, provenance deep-dive, real GitHub PR | `claude -p` auth had expired locally |
| 2026-11-16 19:31 | Implementation plan | 15 min | Full plan with code | Plan scope | - | - |
```

**Step 8: Temporary entry point**

`factory/__main__.py`:
```python
from factory.cli import app

app()
```

(`factory/cli.py` comes in Task 13. Until then `python -m factory` fails. That's expected.)

**Step 9: Create the venv and install**

Run:
```bash
python -m venv .venv
.venv/Scripts/python -m pip install -q -e ".[dev]"
.venv/Scripts/python -c "import typer, pydantic, hypothesis; print('ok')"
```
Expected: `ok`

**Step 10: Renormalize line endings and commit**

```bash
git add -A
git add --renormalize .
git commit -q -m "chore: scaffold repo, LF attributes, agent instructions

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git ls-files --eol | grep -v "i/lf" || echo "all LF"
```
Expected: `all LF` (empty `__init__.py` files show `i/none`, which is fine. The `grep` should list only those.)

---

### Task 2: Sample `orders` module with behaviour and invariant tests

**Files:**
- Create: `orders/order.py`
- Test: `tests/orders/test_order.py`, `tests/invariants/test_order_invariants.py`

**Step 1: Write the behaviour tests**

`tests/orders/test_order.py`:
```python
from decimal import Decimal

import pytest

from orders.order import Order, OrderError, OrderState, Side


def test_new_order_starts_unfilled():
    order = Order("o-1", Side.BUY, Decimal("10"))
    assert order.state is OrderState.NEW
    assert order.remaining == Decimal("10")


def test_partial_then_full_fill():
    order = Order("o-2", Side.SELL, Decimal("10"))
    order.fill(Decimal("4"))
    assert order.state is OrderState.PARTIALLY_FILLED
    order.fill(Decimal("6"))
    assert order.state is OrderState.FILLED
    assert order.remaining == Decimal("0")


def test_overfill_is_rejected_without_mutation():
    order = Order("o-3", Side.BUY, Decimal("5"))
    order.fill(Decimal("3"))
    with pytest.raises(OrderError):
        order.fill(Decimal("3"))
    assert order.filled == Decimal("3")


def test_cancel_new_order():
    order = Order("o-4", Side.BUY, Decimal("5"))
    order.cancel()
    assert order.state is OrderState.CANCELLED


def test_cannot_fill_cancelled_order():
    order = Order("o-5", Side.BUY, Decimal("5"))
    order.cancel()
    with pytest.raises(OrderError):
        order.fill(Decimal("1"))


def test_quantity_must_be_positive():
    with pytest.raises(OrderError):
        Order("o-6", Side.BUY, Decimal("0"))
```

**Step 2: Write the invariant tests (protected path, owned by humans)**

`tests/invariants/test_order_invariants.py`:
```python
"""Order invariants. Owned by humans: agents may not edit this directory.

Property-based: any sequence of fills and cancels must keep every invariant.
"""
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from orders.order import Order, OrderError, OrderState, Side

OPS = st.lists(
    st.one_of(
        st.tuples(st.just("fill"), st.integers(min_value=-2, max_value=12)),
        st.tuples(st.just("cancel"), st.just(0)),
    ),
    max_size=25,
)


@given(quantity=st.integers(min_value=1, max_value=10), ops=OPS)
def test_invariants_hold_for_any_sequence(quantity, ops):
    order = Order("o-1", Side.BUY, Decimal(quantity))
    for op, amount in ops:
        before = (order.filled, order.state)
        try:
            if op == "fill":
                order.fill(Decimal(amount))
            else:
                order.cancel()
        except OrderError:
            assert (order.filled, order.state) == before, "a rejected operation must not mutate the order"
            continue
        filled_before, state_before = before
        assert Decimal(0) <= order.filled <= order.quantity, "filled never exceeds quantity"
        assert order.filled >= filled_before, "filled never decreases"
        assert (order.state is OrderState.FILLED) == (order.filled == order.quantity), "FILLED iff fully filled"
        assert state_before not in (OrderState.FILLED, OrderState.CANCELLED), "terminal states stay terminal"
        if op == "cancel":
            assert order.filled == filled_before, "cancel never changes filled quantity"
```

**Step 3: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/orders tests/invariants -q`
Expected: FAIL / errors with `ModuleNotFoundError: No module named 'orders.order'`

**Step 4: Implement `orders/order.py`**

The exact whitespace matters: the reviewer eval in Task 18 patches these lines.

```python
"""Synthetic order-handling module used as the factory's sample codebase.

Public, synthetic code only. Not based on any real trading system.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class OrderError(Exception):
    """Raised when an operation would break an order invariant."""


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderState(str, Enum):
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"


@dataclass
class Order:
    order_id: str
    side: Side
    quantity: Decimal
    filled: Decimal = field(default=Decimal("0"))
    state: OrderState = OrderState.NEW

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise OrderError("quantity must be positive")

    @property
    def remaining(self) -> Decimal:
        return self.quantity - self.filled

    def fill(self, qty: Decimal) -> None:
        if qty <= 0:
            raise OrderError("fill quantity must be positive")
        if self.state not in (OrderState.NEW, OrderState.PARTIALLY_FILLED):
            raise OrderError(f"cannot fill order in state {self.state.value}")
        if self.filled + qty > self.quantity:
            raise OrderError("fill would exceed order quantity")
        self.filled += qty
        self.state = OrderState.FILLED if self.filled == self.quantity else OrderState.PARTIALLY_FILLED

    def cancel(self) -> None:
        if self.state is not OrderState.NEW:
            raise OrderError(f"cannot cancel order in state {self.state.value}")
        self.state = OrderState.CANCELLED
```

**Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/orders tests/invariants -q`
Expected: `7 passed`

**Step 6: Commit**

```bash
git add orders tests
git commit -q -m "feat(orders): synthetic order module with behaviour and invariant tests

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Errors, schemas and generated spec

**Files:**
- Create: `factory/errors.py`, `factory/schemas.py`, `spec/*.schema.json` (generated)
- Test: `tests/factory/test_schemas.py`

**Step 1: Write the failing tests**

`tests/factory/test_schemas.py`:
```python
from pathlib import Path

import pytest
from pydantic import ValidationError

from factory.schemas import Handoff, Review, export

ROOT = Path(__file__).resolve().parents[2]


def test_handoff_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        Handoff.model_validate({
            "summary": "s", "done": [], "remaining": [], "files_touched": [],
            "tests": "passing", "status": "complete", "mood": "great",
        })


def test_approved_review_cannot_have_blockers():
    with pytest.raises(ValidationError):
        Review.model_validate({
            "verdict": "approved", "summary": "ok",
            "findings": [{"severity": "blocker", "file": "a.py", "message": "broken"}],
        })


def test_spec_files_match_models(tmp_path):
    for generated in export(tmp_path):
        committed = ROOT / "spec" / generated.name
        assert committed.exists(), "run: python -m factory.schemas"
        assert committed.read_text(encoding="utf-8") == generated.read_text(encoding="utf-8"), (
            "spec is stale; run: python -m factory.schemas"
        )
```

**Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/factory/test_schemas.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.schemas'`

**Step 3: Write `factory/errors.py`**

```python
"""Error types. The CLI prints any FactoryError message and exits 1."""


class FactoryError(Exception):
    """Base class for expected, user-facing failures."""


class LedgerError(FactoryError):
    """The ledger file cannot be read or parsed."""


class GitError(FactoryError):
    """A git command failed."""


class WorkflowError(FactoryError):
    """A role was run out of order."""


class AgentRunError(FactoryError):
    """The agent runtime failed to produce a result."""


class AgentOutputError(FactoryError):
    """The agent's final message did not satisfy the output contract."""


class ProtectedPathError(FactoryError):
    """An agent changed files it is not allowed to change."""
```

**Step 4: Write `factory/schemas.py`**

```python
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
```

**Step 5: Generate the spec and run the tests**

Run:
```bash
.venv/Scripts/python -m factory.schemas
.venv/Scripts/python -m pytest tests/factory/test_schemas.py -q
```
Expected: 5 spec paths printed, then `3 passed`

**Step 6: Commit**

```bash
git add factory/errors.py factory/schemas.py spec tests/factory/test_schemas.py
git commit -q -m "feat(factory): protocol schemas and generated JSON Schemas

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Hash-chained ledger

**Files:**
- Create: `factory/ledger.py`
- Test: `tests/factory/test_ledger.py`

**Step 1: Write the failing tests**

`tests/factory/test_ledger.py`:
```python
import pytest

from factory import ledger
from factory.errors import LedgerError
from factory.schemas import Actor


def _append(task_dir, role="initiator", cost=0.0):
    return ledger.append(
        task_dir, task="T-1", role=role, actor=Actor(kind="human", id="alice"),
        on_behalf_of="alice", cost_usd=cost, started_at="t0", ended_at="t1",
    )


def test_append_builds_a_valid_chain(tmp_path):
    first = _append(tmp_path)
    second = _append(tmp_path, role="planner", cost=0.41)
    entries = ledger.load(tmp_path)
    assert [e.seq for e in entries] == [0, 1]
    assert first.prev_hash == ledger.GENESIS
    assert second.prev_hash == first.hash
    assert ledger.check_chain(entries) == []


def test_edited_entry_breaks_the_chain(tmp_path):
    _append(tmp_path)
    _append(tmp_path, role="planner", cost=0.41)
    path = tmp_path / ledger.LEDGER_FILE
    path.write_text(path.read_text(encoding="utf-8").replace("0.41", "0.01"), encoding="utf-8", newline="\n")
    errors = ledger.check_chain(ledger.load(tmp_path))
    assert any("does not match its hash" in e for e in errors)


def test_deleted_entry_breaks_the_chain(tmp_path):
    for _ in range(3):
        _append(tmp_path)
    path = tmp_path / ledger.LEDGER_FILE
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    path.write_text(lines[0] + lines[2], encoding="utf-8", newline="\n")
    errors = ledger.check_chain(ledger.load(tmp_path))
    assert any("prev_hash" in e for e in errors)


def test_invalid_line_raises(tmp_path):
    (tmp_path / ledger.LEDGER_FILE).write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(LedgerError):
        ledger.load(tmp_path)
```

**Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/factory/test_ledger.py -q`
Expected: FAIL with `ImportError: cannot import name 'ledger'`

**Step 3: Implement `factory/ledger.py`**

```python
"""Append-only, hash-chained ledger: one canonical JSON object per line."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .errors import LedgerError
from .schemas import LedgerEntry

GENESIS = "0" * 64
LEDGER_FILE = "ledger.jsonl"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def entry_hash(data: dict[str, Any]) -> str:
    return sha256_bytes(canonical({k: v for k, v in data.items() if k != "hash"}))


def load(task_dir: Path) -> list[LedgerEntry]:
    path = Path(task_dir) / LEDGER_FILE
    if not path.exists():
        return []
    entries = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entries.append(LedgerEntry.model_validate_json(line))
        except ValidationError as exc:
            raise LedgerError(f"{path.name} line {lineno}: invalid entry: {exc}") from exc
    return entries


def append(task_dir: Path, **fields: Any) -> LedgerEntry:
    """Append one entry. seq, prev_hash and hash are computed here, never by callers."""
    entries = load(task_dir)
    data = {**fields, "seq": len(entries), "prev_hash": entries[-1].hash if entries else GENESIS, "hash": ""}
    draft = LedgerEntry.model_validate(data).model_dump(mode="json")
    draft["hash"] = entry_hash(draft)
    entry = LedgerEntry.model_validate(draft)
    with (Path(task_dir) / LEDGER_FILE).open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(canonical(entry.model_dump(mode="json")).decode("utf-8") + "\n")
    return entry


def check_chain(entries: list[LedgerEntry]) -> list[str]:
    errors = []
    prev = GENESIS
    for index, entry in enumerate(entries):
        if entry.seq != index:
            errors.append(f"entry at position {index} has seq {entry.seq}")
        if entry.prev_hash != prev:
            errors.append(f"entry {entry.seq}: prev_hash does not match the previous entry")
        if entry_hash(entry.model_dump(mode="json")) != entry.hash:
            errors.append(f"entry {entry.seq}: content does not match its hash (edited after writing)")
        prev = entry.hash
    return errors
```

**Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/factory/test_ledger.py -q`
Expected: `4 passed`

**Step 5: Commit**

```bash
git add factory/ledger.py tests/factory/test_ledger.py
git commit -q -m "feat(factory): hash-chained append-only ledger

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Git helpers and temp-repo test fixture

**Files:**
- Create: `factory/gitutil.py`, `tests/factory/conftest.py`
- Test: `tests/factory/test_gitutil.py`

**Step 1: Write the fixture**

`tests/factory/conftest.py`:
```python
import subprocess

import pytest


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A small git repo shaped like this one: orders/, protected tests/invariants/, role prompts."""
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    for key, value in [("user.name", "Alice"), ("user.email", "alice@example.com"),
                       ("core.autocrlf", "false"), ("commit.gpgsign", "false")]:
        git(r, "config", key, value)
    write(r / ".gitattributes", "* text=auto eol=lf\n")
    write(r / ".gitignore", "__pycache__/\n.pytest_cache/\n.hypothesis/\n")
    write(r / "orders" / "order.py", "VALUE = 1\n")
    write(r / "tests" / "invariants" / "test_inv.py", "def test_ok():\n    assert True\n")
    for role in ("planner", "implementer", "reviewer"):
        write(r / ".factory" / "roles" / f"{role}.md", f"You are the {role}.\n")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "init")
    monkeypatch.setenv("FACTORY_USER", "alice")
    return r
```

**Step 2: Write the failing tests**

`tests/factory/test_gitutil.py`:
```python
from factory import gitutil

from .conftest import git, write


def test_changed_paths_lists_modified_and_untracked(repo):
    write(repo / "orders" / "order.py", "VALUE = 2\n")
    write(repo / "orders" / "new" / "deep.py", "x = 1\n")
    assert gitutil.changed_paths(repo) == ["orders/new/deep.py", "orders/order.py"]


def test_commit_all_except_factory_leaves_factory_changes(repo):
    write(repo / "orders" / "order.py", "VALUE = 2\n")
    write(repo / ".factory" / "tasks" / "T-1" / "x.json", "{}\n")
    sha = gitutil.commit_all_except_factory(repo, "code")
    assert gitutil.files_in_commit(repo, sha) == ["orders/order.py"]
    assert gitutil.changed_paths(repo) == [".factory/tasks/T-1/x.json"]


def test_commits_between_and_parents(repo):
    base = gitutil.head(repo)
    write(repo / "a.txt", "a\n")
    first = gitutil.commit_paths(repo, ["a.txt"], "a")
    write(repo / "b.txt", "b\n")
    second = gitutil.commit_paths(repo, ["b.txt"], "b")
    assert gitutil.commits_between(repo, base) == [first, second]
    assert gitutil.parents(repo, second) == [first]
    assert gitutil.is_ancestor(repo, first)
    git(repo, "checkout", "-q", "-b", "other", base)
    assert not gitutil.is_ancestor(repo, second)


def test_diff_excludes_factory(repo):
    base = gitutil.head(repo)
    write(repo / "orders" / "order.py", "VALUE = 3\n")
    write(repo / ".factory" / "tasks" / "T-1" / "x.json", "{}\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "both")
    diff = gitutil.diff(repo, base, "HEAD")
    assert "orders/order.py" in diff
    assert ".factory" not in diff
```

**Step 3: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/factory/test_gitutil.py -q`
Expected: FAIL with `ImportError: cannot import name 'gitutil'`

**Step 4: Implement `factory/gitutil.py`**

```python
"""Thin wrappers over the git CLI. All paths are repo-relative POSIX strings."""
from __future__ import annotations

import subprocess
from pathlib import Path

from .errors import GitError

EXCLUDE_FACTORY = ":(exclude).factory"


def git(repo: Path, *args: str, strip: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip() if strip else proc.stdout


def repo_root(start: Path) -> Path:
    return Path(git(start, "rev-parse", "--show-toplevel"))


def head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD")


def current_branch(repo: Path) -> str:
    return git(repo, "rev-parse", "--abbrev-ref", "HEAD")


def config(repo: Path, key: str) -> str | None:
    try:
        return git(repo, "config", key) or None
    except GitError:
        return None


def changed_paths(repo: Path) -> list[str]:
    """Modified, staged, deleted and untracked (non-ignored) files."""
    out = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all", strip=False)
    parts = out.split("\0")
    paths: list[str] = []
    i = 0
    while i < len(parts):
        item = parts[i]
        if not item:
            i += 1
            continue
        status, path = item[:2], item[3:]
        paths.append(path)
        if status[0] in "RC":
            paths.append(parts[i + 1])
            i += 2
        else:
            i += 1
    return sorted(set(paths))


def commits_between(repo: Path, base: str, tip: str = "HEAD") -> list[str]:
    out = git(repo, "rev-list", "--reverse", f"{base}..{tip}")
    return out.splitlines() if out else []


def parents(repo: Path, sha: str) -> list[str]:
    return git(repo, "rev-list", "--parents", "-n", "1", sha).split()[1:]


def files_in_commit(repo: Path, sha: str) -> list[str]:
    out = git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", "-z", sha, strip=False)
    return [p for p in out.split("\0") if p]


def is_ancestor(repo: Path, ancestor: str, tip: str = "HEAD") -> bool:
    proc = subprocess.run(["git", "merge-base", "--is-ancestor", ancestor, tip], cwd=repo, capture_output=True)
    return proc.returncode == 0


def diff(repo: Path, base: str, tip: str) -> str:
    return git(repo, "diff", base, tip, "--", ".", EXCLUDE_FACTORY, strip=False)


def working_diff(repo: Path) -> str:
    return git(repo, "diff", "HEAD", "--", ".", EXCLUDE_FACTORY, strip=False)


def commit_all_except_factory(repo: Path, message: str) -> str:
    git(repo, "add", "-A", "--", ".", EXCLUDE_FACTORY)
    git(repo, "commit", "-q", "-m", message)
    return head(repo)


def commit_paths(repo: Path, paths: list[str], message: str) -> str:
    git(repo, "add", "--", *paths)
    git(repo, "commit", "-q", "-m", message)
    return head(repo)
```

**Step 5: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/factory/test_gitutil.py -q`
Expected: `4 passed`

**Step 6: Commit**

```bash
git add factory/gitutil.py tests/factory/conftest.py tests/factory/test_gitutil.py
git commit -q -m "feat(factory): git helpers and temp-repo fixture

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Workflow state machine

**Files:**
- Create: `factory/workflow.py`
- Test: `tests/factory/test_workflow.py`

**Step 1: Write the failing tests**

`tests/factory/test_workflow.py`:
```python
from factory.schemas import AGENT_ROLES, Actor, LedgerEntry
from factory.workflow import allowed_next, describe_state, is_pr_ready, sequence_errors


def chain(*roles):
    return [
        LedgerEntry(seq=i, task="T-1", role=role,
                    actor=Actor(kind="agent" if role in AGENT_ROLES else "human", id="x"),
                    on_behalf_of="alice", started_at="t", ended_at="t", prev_hash="p", hash="h")
        for i, role in enumerate(roles)
    ]


def verdicts(mapping):
    return lambda entry: mapping.get(entry.seq)


HAPPY = ("initiator", "planner", "plan_approval", "implementer", "reviewer")


def test_happy_sequence_is_valid_and_pr_ready():
    entries = chain(*HAPPY)
    v = verdicts({4: "approved"})
    assert sequence_errors(entries, v, 3) == []
    assert is_pr_ready(entries, v)
    assert describe_state(entries, v, 3).startswith("approved")


def test_reviewer_cannot_run_before_implementation():
    entries = chain("initiator", "planner", "plan_approval")
    assert "reviewer" not in allowed_next(entries, verdicts({}), 3)


def test_skipping_plan_approval_is_flagged():
    entries = chain("initiator", "planner", "implementer", "reviewer")
    errors = sequence_errors(entries, verdicts({3: "approved"}), 3)
    assert any("entry 2" in e for e in errors)


def test_review_loop_limit_hands_over_to_a_human():
    entries = chain("initiator", "planner", "plan_approval", "implementer", "reviewer", "implementer", "reviewer")
    v = verdicts({4: "changes_requested", 6: "changes_requested"})
    assert allowed_next(entries, v, 2) == {"human_change"}
    assert allowed_next(entries, v, 3) == {"implementer", "human_change"}
    assert not is_pr_ready(entries, v)
```

**Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/factory/test_workflow.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.workflow'`

**Step 3: Implement `factory/workflow.py`**

```python
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
```

**Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/factory/test_workflow.py -q`
Expected: `4 passed`

**Step 5: Commit**

```bash
git add factory/workflow.py tests/factory/test_workflow.py
git commit -q -m "feat(factory): workflow state machine

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Agent runtimes (Claude Code headless and fake)

**Files:**
- Create: `factory/runtime.py`
- Test: `tests/factory/test_runtime.py`

**Step 1: Write the failing tests**

`tests/factory/test_runtime.py`:
```python
import json

import pytest

from factory.errors import AgentOutputError, AgentRunError
from factory.runtime import (ClaudeRuntime, FakeRuntime, FakeStep, ToolPolicy,
                             extract_json_block, parse_claude_output)


def test_extract_json_block_takes_the_last_block():
    text = 'thinking\n```json\n{"a": 1}\n```\nmore\n```json\n{"b": 2}\n```\n'
    assert extract_json_block(text) == {"b": 2}


def test_extract_json_block_rejects_prose():
    with pytest.raises(AgentOutputError):
        extract_json_block("I am done, everything works.")


def test_parse_claude_output_reads_cost_model_and_tokens():
    stdout = json.dumps({
        "type": "result", "subtype": "success", "is_error": False, "result": "ok",
        "session_id": "s-1", "total_cost_usd": 0.42,
        "usage": {"input_tokens": 10, "cache_read_input_tokens": 90, "cache_creation_input_tokens": 0,
                  "output_tokens": 7},
        "modelUsage": {"claude-haiku-x": {"costUSD": 0.02}, "claude-sonnet-x": {"costUSD": 0.40}},
        "permission_denials": [{"tool_name": "Edit", "tool_input": {}}],
    })
    result = parse_claude_output(stdout)
    assert result.model == "claude-sonnet-x"
    assert result.cost_usd == pytest.approx(0.42)
    assert (result.tokens_in, result.tokens_out) == (100, 7)
    assert result.denials == ["Edit"]


def test_parse_claude_output_raises_on_error_even_with_success_subtype():
    stdout = json.dumps({"type": "result", "subtype": "success", "is_error": True,
                         "result": "Failed to authenticate"})
    with pytest.raises(AgentRunError, match="authenticate"):
        parse_claude_output(stdout)


def test_claude_command_isolates_settings_and_passes_tool_rules():
    cmd = ClaudeRuntime(model="sonnet").command(
        ToolPolicy(allowed=("Read", "Bash(python -m pytest:*)"), denied=("Edit(tests/invariants/**)",)))
    assert cmd[:2] == ["claude", "-p"]
    assert ["--setting-sources", "project"] == cmd[cmd.index("--setting-sources"):cmd.index("--setting-sources") + 2]
    assert "--strict-mcp-config" in cmd
    i = cmd.index("--allowedTools")
    assert cmd[i + 1:i + 3] == ["Read", "Bash(python -m pytest:*)"]
    assert cmd[cmd.index("--disallowedTools") + 1] == "Edit(tests/invariants/**)"


def test_fake_runtime_writes_files_and_picks_step_by_attempt(tmp_path):
    rt = FakeRuntime({"implementer": [FakeStep("one", files={"a/b.py": "x = 1\n"}), FakeStep("two")]})
    first = rt.run(role="implementer", prompt="p", policy=ToolPolicy(()), cwd=tmp_path, attempt=0)
    second = rt.run(role="implementer", prompt="p", policy=ToolPolicy(()), cwd=tmp_path, attempt=1)
    assert (first.text, second.text) == ("one", "two")
    assert (tmp_path / "a" / "b.py").read_text() == "x = 1\n"
    with pytest.raises(AgentRunError):
        rt.run(role="implementer", prompt="p", policy=ToolPolicy(()), cwd=tmp_path, attempt=2)


def test_fake_runtime_from_dir(tmp_path):
    (tmp_path / "planner-1.md").write_text("plan", encoding="utf-8")
    (tmp_path / "implementer-2.md").write_text("second", encoding="utf-8")
    (tmp_path / "implementer-1.md").write_text("first", encoding="utf-8")
    (tmp_path / "implementer-1.files" / "orders").mkdir(parents=True)
    (tmp_path / "implementer-1.files" / "orders" / "order.py").write_text("V = 2\n", encoding="utf-8")
    rt = FakeRuntime.from_dir(tmp_path)
    assert [s.text for s in rt.steps["implementer"]] == ["first", "second"]
    assert rt.steps["implementer"][0].files == {"orders/order.py": "V = 2\n"}
```

**Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/factory/test_runtime.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.runtime'`

**Step 3: Implement `factory/runtime.py`**

```python
"""Agent runtimes. A runtime runs one role once and returns its final message plus usage."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .errors import AgentOutputError, AgentRunError


@dataclass(frozen=True)
class ToolPolicy:
    allowed: tuple[str, ...]
    denied: tuple[str, ...] = ()


@dataclass
class RunResult:
    text: str
    model: str
    runtime: str
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    session_id: str | None = None
    denials: list[str] = field(default_factory=list)


class Runtime(Protocol):
    name: str

    def run(self, *, role: str, prompt: str, policy: ToolPolicy, cwd: Path, attempt: int) -> RunResult: ...


_JSON_BLOCK = re.compile(r"```json[ \t]*\r?\n(.*?)\r?\n```", re.DOTALL)


def extract_json_block(text: str) -> dict:
    blocks = _JSON_BLOCK.findall(text)
    candidate = blocks[-1] if blocks else text.strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise AgentOutputError(f"final message has no valid ```json block: {exc}") from exc
    if not isinstance(value, dict):
        raise AgentOutputError("the ```json block must contain a JSON object")
    return value


def parse_claude_output(stdout: str) -> RunResult:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise AgentRunError(f"claude returned non-JSON output: {stdout[:300]!r}") from exc
    if isinstance(data, list):
        data = next((d for d in reversed(data) if isinstance(d, dict) and d.get("type") == "result"), {})
    if data.get("is_error") or data.get("subtype") != "success":
        raise AgentRunError(f"agent run failed ({data.get('subtype')}): {str(data.get('result', ''))[:500]}")
    usage = data.get("usage") or {}
    model_usage = data.get("modelUsage") or {}
    model = max(model_usage, key=lambda m: model_usage[m].get("costUSD", 0)) if model_usage else "unknown"
    tokens_in = sum(int(usage.get(k) or 0)
                    for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    denials = [str(d.get("tool_name")) if isinstance(d, dict) else str(d)
               for d in data.get("permission_denials") or []]
    return RunResult(
        text=str(data.get("result", "")), model=model, runtime="claude-code",
        cost_usd=float(data.get("total_cost_usd") or 0), tokens_in=tokens_in,
        tokens_out=int(usage.get("output_tokens") or 0), session_id=data.get("session_id"), denials=denials,
    )


class ClaudeRuntime:
    """Runs a role as headless Claude Code, isolated from the user's personal settings and MCP servers."""

    name = "claude-code"

    def __init__(self, model: str | None = None, executable: str = "claude", timeout_s: int = 1800):
        self.model = model
        self.executable = executable
        self.timeout_s = timeout_s

    def command(self, policy: ToolPolicy) -> list[str]:
        cmd = [self.executable, "-p", "--output-format", "json", "--permission-mode", "default",
               "--setting-sources", "project", "--strict-mcp-config", "--no-session-persistence"]
        if self.model:
            cmd += ["--model", self.model]
        cmd += ["--allowedTools", *policy.allowed]
        if policy.denied:
            cmd += ["--disallowedTools", *policy.denied]
        return cmd

    def run(self, *, role: str, prompt: str, policy: ToolPolicy, cwd: Path, attempt: int) -> RunResult:
        exe = shutil.which(self.executable)
        if exe is None:
            raise AgentRunError(f"'{self.executable}' not found on PATH; install Claude Code or use --runtime fake")
        cmd = self.command(policy)
        cmd[0] = exe
        try:
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                                  cwd=cwd, timeout=self.timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise AgentRunError(f"{role} timed out after {self.timeout_s}s") from exc
        if not proc.stdout.strip():
            raise AgentRunError(f"{role} produced no output (exit {proc.returncode}): {proc.stderr.strip()[:500]}")
        return parse_claude_output(proc.stdout)


@dataclass
class FakeStep:
    text: str
    files: dict[str, str] = field(default_factory=dict)
    model: str = "fake-model"
    cost_usd: float = 0.0
    error: str | None = None


class FakeRuntime:
    """Deterministic runtime: replays scripted final messages and file writes. Used by tests and as demo fallback."""

    name = "fake"

    def __init__(self, steps: dict[str, list[FakeStep]]):
        self.steps = steps

    def run(self, *, role: str, prompt: str, policy: ToolPolicy, cwd: Path, attempt: int) -> RunResult:
        queue = self.steps.get(role, [])
        if attempt >= len(queue):
            raise AgentRunError(f"fake runtime has no step {attempt + 1} for role {role}")
        step = queue[attempt]
        if step.error:
            raise AgentRunError(step.error)
        for rel, content in step.files.items():
            target = Path(cwd) / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        return RunResult(text=step.text, model=step.model, runtime=self.name, cost_usd=step.cost_usd)

    @classmethod
    def from_dir(cls, directory: Path) -> "FakeRuntime":
        """Load <role>-<n>.md final messages and optional <role>-<n>.files/ trees."""
        directory = Path(directory)
        found: dict[str, list[tuple[int, FakeStep]]] = {}
        for md in sorted(directory.glob("*-*.md")):
            role, _, number = md.stem.rpartition("-")
            files_dir = directory / f"{md.stem}.files"
            files = {}
            if files_dir.is_dir():
                files = {p.relative_to(files_dir).as_posix(): p.read_text(encoding="utf-8")
                         for p in sorted(files_dir.rglob("*")) if p.is_file()}
            found.setdefault(role, []).append((int(number), FakeStep(md.read_text(encoding="utf-8"), files)))
        return cls({role: [s for _, s in sorted(items, key=lambda t: t[0])] for role, items in found.items()})


def get_runtime(name: str | None = None, model: str | None = None) -> Runtime:
    name = name or os.environ.get("FACTORY_RUNTIME", "claude")
    if name == "claude":
        return ClaudeRuntime(model=model or os.environ.get("FACTORY_MODEL"))
    if name == "fake":
        directory = os.environ.get("FACTORY_FAKE_DIR")
        if not directory:
            raise AgentRunError("FACTORY_FAKE_DIR must point at a directory of fake runs (see demo/fake)")
        return FakeRuntime.from_dir(Path(directory))
    raise AgentRunError(f"unknown runtime {name!r}; use 'claude' or 'fake'")
```

**Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/factory/test_runtime.py -q`
Expected: `7 passed`

**Step 5: Commit**

```bash
git add factory/runtime.py tests/factory/test_runtime.py
git commit -q -m "feat(factory): claude headless and fake runtimes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Role prompts, prompt builder and tool policies

**Files:**
- Create: `factory/prompts.py`, `.factory/roles/planner.md`, `.factory/roles/implementer.md`, `.factory/roles/reviewer.md`
- Test: `tests/factory/test_prompts.py`

**Step 1: Write the failing tests**

`tests/factory/test_prompts.py`:
```python
from factory.prompts import build_prompt, policy_for
from factory.schemas import Handoff, Task

TASK = Task(id="T-1", title="t", goal="g", initiator="alice", base_commit="a" * 40,
            branch="factory/T-1", created_at="now")


def test_prompt_contains_sections_and_output_schema():
    prompt = build_prompt("ROLE TEXT", [("Task", "do the thing")], Handoff)
    assert prompt.startswith("ROLE TEXT")
    assert "## Task\n\ndo the thing" in prompt
    assert '"files_touched"' in prompt


def test_implementer_cannot_edit_protected_paths_or_factory():
    policy = policy_for("implementer", TASK)
    assert "Edit" in policy.allowed
    assert "Edit(tests/invariants/**)" in policy.denied
    assert "Write(.factory/**)" in policy.denied


def test_planner_is_read_only():
    policy = policy_for("planner", TASK)
    assert set(policy.allowed) == {"Read", "Grep", "Glob"}


def test_reviewer_cannot_read_task_folders():
    policy = policy_for("reviewer", TASK)
    assert "Read(.factory/tasks/**)" in policy.denied
    assert "Edit" in policy.denied
```

**Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/factory/test_prompts.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.prompts'`

**Step 3: Implement `factory/prompts.py`**

```python
"""Builds role prompts and per-role tool policies."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from .runtime import ToolPolicy
from .schemas import Task

ROLES_DIR = Path(".factory") / "roles"
READ_TOOLS = ("Read", "Grep", "Glob")
PYTEST = "Bash(python -m pytest:*)"


def role_prompt_path(repo: Path, role: str) -> Path:
    return Path(repo) / ROLES_DIR / f"{role}.md"


def build_prompt(role_text: str, sections: list[tuple[str, str]], output_model: type[BaseModel]) -> str:
    parts = [role_text.strip(), ""]
    for title, body in sections:
        parts += [f"## {title}", "", body.strip(), ""]
    parts += [
        "## Output contract", "",
        "End your final message with exactly one fenced ```json block that validates against this "
        "JSON Schema. Write nothing after the block.", "",
        "```json", json.dumps(output_model.model_json_schema(), indent=2), "```", "",
    ]
    return "\n".join(parts)


def policy_for(role: str, task: Task) -> ToolPolicy:
    protected = [*task.protected_paths, ".factory/**"]
    if role == "planner":
        return ToolPolicy(allowed=READ_TOOLS, denied=("Edit", "Write", "Bash"))
    if role == "implementer":
        denied = tuple(f"{tool}({path})" for path in protected for tool in ("Edit", "Write"))
        return ToolPolicy(allowed=(*READ_TOOLS, "Edit", "Write", PYTEST), denied=denied)
    if role == "reviewer":
        return ToolPolicy(allowed=(*READ_TOOLS, PYTEST), denied=("Edit", "Write", "Read(.factory/tasks/**)"))
    raise ValueError(f"no tool policy for role {role!r}")
```

**Step 4: Write the role prompts**

`.factory/roles/planner.md`:
```markdown
# Role: Planner

You plan one change in a regulated trading codebase. You do not write code.

- Read the task and the relevant code first. You have Read, Grep and Glob only.
- Plan the smallest change that meets the goal.
- Name every invariant the change could affect, for example "filled quantity never exceeds order quantity".
  Invariant tests in protected paths belong to humans. If a new invariant test is needed, say so in
  risks; agents will not write it.
- The test plan lists the behaviour tests the implementer must add or change.
- If the task is ambiguous, say so in risks. Do not guess.
```

`.factory/roles/implementer.md`:
```markdown
# Role: Implementer

You implement an approved plan. A different agent reviews your diff without seeing your notes,
and a human approves the pull request.

- Follow the approved plan. If the plan is wrong, stop and explain in open_questions.
  Do not invent a different design.
- Never edit the protected paths named in the task (for example tests/invariants/) or anything
  under .factory/. Such edits are blocked and fail the run.
- Add or update behaviour tests for your change under tests/ (outside protected paths).
- Run `python -m pytest -q` before you finish and report the result honestly in "tests".
- Do not commit. The factory commits for you.
- If you are resuming, start from the previous hand-off and any uncommitted diff. Do not redo finished work.
- If you run low on context or time, stop at a clean point, set status "in_progress" and list exactly
  what remains. The next session starts only from your hand-off.
```

`.factory/roles/reviewer.md`:
```markdown
# Role: Reviewer

You review a diff against its task and approved plan. You did not write it and you cannot see the
implementer's notes. That is deliberate.

- Judge the diff, not the intent. Read the surrounding code with Read, Grep and Glob.
- Check every invariant named in the plan, and any order-handling invariant the diff could break:
  filled never exceeds quantity; filled never decreases; FILLED and CANCELLED are terminal;
  a rejected operation does not change the order.
- Check that tests cover the new behaviour and assert what the code should do, not only what it does.
- Flag secrets, credentials, and network or file access that the task does not need.
- You may run `python -m pytest -q`. You cannot edit files.
- Use verdict "approved" only if you have no blocker or major finding. Otherwise use
  "changes_requested" with findings the implementer can act on.
```

**Step 5: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/factory/test_prompts.py -q`
Expected: `4 passed`

**Step 6: Commit**

```bash
git add factory/prompts.py .factory/roles tests/factory/test_prompts.py
git commit -q -m "feat(factory): role prompts, prompt builder, per-role tool policies

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Core — new task, planner, plan approval

**Files:**
- Create: `factory/core.py`, `tests/factory/helpers.py`
- Test: `tests/factory/test_core.py`

**Step 1: Write the test helpers**

`tests/factory/helpers.py`:
```python
import json

from factory import core
from factory.runtime import FakeRuntime, FakeStep

PLAN = {"summary": "Allow cancelling partially filled orders", "steps": ["Relax the state check in cancel()"],
        "invariants_affected": ["cancel never changes filled quantity"], "test_plan": ["test partial cancel"]}
HANDOFF = {"summary": "Implemented partial cancel", "done": ["cancel()"], "remaining": [],
           "files_touched": ["orders/order.py"], "tests": "passing", "status": "complete"}
HANDOFF_WIP = {**HANDOFF, "summary": "Code changed, tests pending", "remaining": ["add test"],
               "tests": "not_run", "status": "in_progress"}
REVIEW_OK = {"verdict": "approved", "summary": "Correct and tested", "findings": [],
             "invariants_checked": ["filled <= quantity"]}
REVIEW_NO = {"verdict": "changes_requested", "summary": "Missing test",
             "findings": [{"severity": "major", "file": "orders/order.py", "message": "add a test"}]}


def block(obj) -> str:
    return "Done.\n\n```json\n" + json.dumps(obj, indent=2) + "\n```\n"


def fake(**overrides) -> FakeRuntime:
    steps = {
        "planner": [FakeStep(block(PLAN))],
        "implementer": [FakeStep(block(HANDOFF), files={"orders/order.py": "VALUE = 2\n"})],
        "reviewer": [FakeStep(block(REVIEW_OK))],
    }
    steps.update(overrides)
    return FakeRuntime(steps)


class RecordingRuntime(FakeRuntime):
    def __init__(self, steps):
        super().__init__(steps)
        self.prompts: list[tuple[str, str]] = []

    def run(self, **kwargs):
        self.prompts.append((kwargs["role"], kwargs["prompt"]))
        return super().run(**kwargs)


def tests_pass(repo):
    return True, "1 passed"


def tests_fail(repo):
    return False, "1 failed"


def start(repo, runtime=None):
    """New task, planned and plan-approved."""
    rt = runtime or fake()
    ref = core.new_task(repo, "Cancel partial fills", "Allow cancelling the remaining quantity", task_id="T-001")
    core.run_planner(ref, rt)
    core.approve_plan(ref)
    return ref, rt


def happy_path(repo, runtime=None):
    ref, rt = start(repo, runtime)
    core.run_implementer(ref, rt)
    core.run_reviewer(ref, rt, test_runner=tests_pass)
    return ref
```

**Step 2: Write the failing tests**

`tests/factory/test_core.py`:
```python
import pytest

from factory import core, gitutil, ledger
from factory.errors import AgentOutputError, WorkflowError

from .helpers import fake, start
from .conftest import write


def test_new_task_creates_branch_task_file_and_initiator_entry(repo):
    ref = core.new_task(repo, "Cancel partial fills", "goal", task_id="T-001")
    assert gitutil.current_branch(repo) == "factory/T-001"
    task = core.load_task(ref)
    assert task.initiator == "alice"
    [entry] = ledger.load(ref.dir)
    assert (entry.role, entry.actor.kind) == ("initiator", "human")
    assert gitutil.changed_paths(repo) == []


def test_planner_writes_plan_and_approval_is_recorded(repo):
    ref, _ = start(repo)
    roles = [e.role for e in ledger.load(ref.dir)]
    assert roles == ["initiator", "planner", "plan_approval"]
    plan = ref.path("plan.md").read_text(encoding="utf-8")
    assert "Relax the state check" in plan
    planner = ledger.load(ref.dir)[1]
    assert planner.actor.kind == "agent" and planner.role_prompt_sha256
    assert planner.on_behalf_of == "alice"


def test_approver_edit_to_plan_is_recorded(repo):
    rt = fake()
    ref = core.new_task(repo, "t", "g", task_id="T-001")
    core.run_planner(ref, rt)
    with ref.path("plan.md").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write("- extra step added by a human\n")
    entry = core.approve_plan(ref, user="bob")
    assert entry.note.startswith("approver edited the plan")
    assert entry.inputs["plan.md"] != entry.outputs["plan.md"]
    assert entry.actor.id == "bob"


def test_roles_cannot_run_out_of_order(repo):
    ref = core.new_task(repo, "t", "g", task_id="T-001")
    with pytest.raises(WorkflowError):
        core.run_reviewer(ref, fake())


def test_invalid_agent_output_writes_no_entry(repo):
    from factory.runtime import FakeStep
    ref = core.new_task(repo, "t", "g", task_id="T-001")
    with pytest.raises(AgentOutputError):
        core.run_planner(ref, fake(planner=[FakeStep("I planned it, trust me.")]))
    assert [e.role for e in ledger.load(ref.dir)] == ["initiator"]
```

**Step 3: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/factory/test_core.py -q`
Expected: FAIL with `ImportError: cannot import name 'core'`

**Step 4: Implement `factory/core.py` (part 1)**

```python
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
```

**Step 5: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/factory/test_core.py -q`
Expected: `5 passed`

**Step 6: Commit**

```bash
git add factory/core.py tests/factory/helpers.py tests/factory/test_core.py
git commit -q -m "feat(factory): new task, planner and human plan gate

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Core — implementer sessions and human changes

**Files:**
- Modify: `factory/core.py` (append functions)
- Test: `tests/factory/test_core_implementer.py`

**Step 1: Write the failing tests**

`tests/factory/test_core_implementer.py`:
```python
import pytest

from factory import core, gitutil, ledger
from factory.errors import ProtectedPathError
from factory.runtime import FakeStep

from .conftest import write
from .helpers import HANDOFF, HANDOFF_WIP, RecordingRuntime, block, fake, start


def test_implementer_commits_code_with_trailers_then_ledger(repo):
    ref, rt = start(repo)
    entry = core.run_implementer(ref, rt)
    [code_commit] = entry.commits
    assert gitutil.files_in_commit(repo, code_commit) == ["orders/order.py"]
    message = gitutil.git(repo, "log", "-1", "--format=%B", code_commit)
    assert "Factory-Role: implementer" in message
    assert "Co-authored-by: fake (fake-model)" in message
    assert ref.path("handoff-001.json").exists()
    assert gitutil.changed_paths(repo) == []


def test_second_session_resumes_from_previous_handoff(repo):
    rt = RecordingRuntime({
        **fake().steps,
        "implementer": [FakeStep(block(HANDOFF_WIP), files={"orders/order.py": "VALUE = 2\n"}),
                        FakeStep(block(HANDOFF), files={"tests/test_more.py": "def test_x():\n    pass\n"})],
    })
    ref, _ = start(repo, rt)
    core.run_implementer(ref, rt)
    core.run_implementer(ref, rt)
    second_prompt = [p for role, p in rt.prompts if role == "implementer"][1]
    assert "Previous hand-off" in second_prompt and "Code changed, tests pending" in second_prompt
    assert ref.path("handoff-002.json").exists()
    assert ledger.load(ref.dir)[-1].inputs["handoff-001.json"]


def test_protected_path_edit_fails_and_records_nothing(repo):
    rt = fake(implementer=[FakeStep(block(HANDOFF), files={"tests/invariants/test_inv.py": "# weakened\n"})])
    ref, _ = start(repo, rt)
    with pytest.raises(ProtectedPathError):
        core.run_implementer(ref, rt)
    assert [e.role for e in ledger.load(ref.dir)][-1] == "plan_approval"


def test_record_human_change(repo):
    ref, _ = start(repo)
    write(repo / "orders" / "order.py", "VALUE = 42\n")
    entry = core.record_human(ref, "manual fix", user="alice")
    assert entry.role == "human_change" and entry.actor.kind == "human"
    assert gitutil.files_in_commit(repo, entry.commits[0]) == ["orders/order.py"]
```

**Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/factory/test_core_implementer.py -q`
Expected: FAIL with `AttributeError: module 'factory.core' has no attribute 'run_implementer'`

**Step 3: Append to `factory/core.py`**

```python
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
```

**Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/factory -q`
Expected: all pass (`test_core_implementer.py`: 4 passed)

**Step 5: Commit**

```bash
git add factory/core.py tests/factory/test_core_implementer.py
git commit -q -m "feat(factory): implementer sessions with hand-offs, human change records

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Core — blind reviewer with factory-run tests

**Files:**
- Modify: `factory/core.py` (append)
- Test: `tests/factory/test_core_reviewer.py`

**Step 1: Write the failing tests**

`tests/factory/test_core_reviewer.py`:
```python
from factory import core, ledger
from factory.runtime import FakeStep
from factory.schemas import Review

from .helpers import REVIEW_NO, RecordingRuntime, block, fake, start, tests_fail, tests_pass


def test_reviewer_sees_diff_but_not_implementer_notes(repo):
    rt = RecordingRuntime(fake().steps)
    ref, _ = start(repo, rt)
    core.run_implementer(ref, rt)
    entry = core.run_reviewer(ref, rt, test_runner=tests_pass)
    prompt = [p for role, p in rt.prompts if role == "reviewer"][0]
    assert "VALUE = 2" in prompt
    assert "Implemented partial cancel" not in prompt
    assert entry.outputs.keys() == {"review-001.json"}
    assert entry.note.startswith("factory test run passed")


def test_failing_tests_override_an_approval(repo):
    ref, rt = start(repo)
    core.run_implementer(ref, rt)
    core.run_reviewer(ref, rt, test_runner=tests_fail)
    review = Review.model_validate_json(ref.path("review-001.json").read_text(encoding="utf-8"))
    assert review.verdict == "changes_requested"
    assert review.findings[0].severity == "blocker"


def test_changes_requested_feeds_next_implementer_session(repo):
    rt = RecordingRuntime({
        **fake().steps,
        "implementer": fake().steps["implementer"] * 2,
        "reviewer": [FakeStep(block(REVIEW_NO))],
    })
    ref, _ = start(repo, rt)
    core.run_implementer(ref, rt)
    core.run_reviewer(ref, rt, test_runner=tests_pass)
    core.run_implementer(ref, rt)
    second = [p for role, p in rt.prompts if role == "implementer"][1]
    assert "Reviewer findings to address" in second and "add a test" in second
    assert "review-001.json" in ledger.load(ref.dir)[-1].inputs
```

Note: in the third test the second implementer step writes the same content, so it produces no code commit. That's fine.

**Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/factory/test_core_reviewer.py -q`
Expected: FAIL with `AttributeError: ... 'run_reviewer'`

**Step 3: Append to `factory/core.py`**

```python
def run_tests(repo: Path, command: list[str]) -> tuple[bool, str]:
    cmd = [sys.executable if i == 0 and part == "python" else part for i, part in enumerate(command)]
    proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, encoding="utf-8", timeout=900)
    lines = (proc.stdout + proc.stderr).splitlines()
    return proc.returncode == 0, "\n".join(lines[-60:])


def run_reviewer(ref: TaskRef, runtime: Runtime, test_runner: TestRunner | None = None) -> LedgerEntry:
    task, entries = _require(ref, "reviewer")
    _require_clean(ref.repo)
    head = gitutil.head(ref.repo)
    tests_ok, test_log = (test_runner or (lambda repo: run_tests(repo, task.test_command)))(ref.repo)
    sections = [
        ("Task", _read(ref, "task.json")),
        ("Approved plan", _read(ref, "plan.md")),
        ("Diff under review", f"```diff\n{gitutil.diff(ref.repo, task.base_commit, head)}\n```"),
        ("Test run by the factory", f"result: {'PASSED' if tests_ok else 'FAILED'}\n\n```\n{test_log}\n```"),
    ]
    review, result, role_sha, started = _call_agent(ref, task, entries, "reviewer", runtime, sections, Review)
    _reject_changes(ref, "reviewer")
    note = f"factory test run {'passed' if tests_ok else 'failed'}"
    if not tests_ok and review.verdict == "approved":
        review = Review(
            verdict="changes_requested",
            summary=f"[factory override] the test suite failed; the agent verdict was 'approved'. {review.summary}",
            findings=[Finding(severity="blocker", file="(test suite)", message="factory test run failed"),
                      *review.findings],
            invariants_checked=review.invariants_checked,
        )
        note += "; agent approval overridden"
    name = f"review-{sum(1 for e in entries if e.role == 'reviewer') + 1:03d}.json"
    _write_model(ref.path(name), review)
    entry = ledger.append(ref.dir, **_agent_fields(
        ref, task, "reviewer", result, role_sha, started,
        inputs={**_hash_of(ref, "task.json", "plan.md"), "head": head},
        outputs=_hash_of(ref, name), commits=[], note=note))
    _commit_ledger(ref, entry, [name])
    return entry
```

**Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/factory -q`
Expected: all pass

**Step 5: Commit**

```bash
git add factory/core.py tests/factory/test_core_reviewer.py
git commit -q -m "feat(factory): blind reviewer with factory-run tests and approval override

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: `verify` — the provenance checker

**Files:**
- Create: `factory/verify.py`
- Test: `tests/factory/test_verify.py`

**Step 1: Write the failing tests (one tamper case per check)**

`tests/factory/test_verify.py`:
```python
from factory import core, gitutil, ledger
from factory.schemas import Actor
from factory.verify import verify

from .conftest import git, write
from .helpers import happy_path, start


def failing(report):
    return {c.name for c in report.checks if not c.ok}


def test_happy_path_passes(repo):
    ref = happy_path(repo)
    report = verify(repo, ref.task_id)
    assert report.ok, report.render()


def test_edited_ledger_line_is_detected(repo):
    ref = happy_path(repo)
    path = ref.path("ledger.jsonl")
    text = path.read_text(encoding="utf-8").replace('"on_behalf_of":"alice"', '"on_behalf_of":"mallory"', 1)
    path.write_text(text, encoding="utf-8", newline="\n")
    git(repo, "commit", "-qam", "tamper")
    assert "ledger hash chain intact" in failing(verify(repo, ref.task_id))


def test_plan_edited_after_approval_is_detected(repo):
    ref = happy_path(repo)
    with ref.path("plan.md").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write("- sneaky extra scope\n")
    git(repo, "commit", "-qam", "edit plan")
    assert "task files match the ledger (chain of custody)" in failing(verify(repo, ref.task_id))


def test_unrecorded_code_commit_is_detected(repo):
    ref = happy_path(repo)
    write(repo / "orders" / "order.py", "VALUE = 99\n")
    git(repo, "commit", "-qam", "quick fix")
    failed = failing(verify(repo, ref.task_id))
    assert "every code commit is claimed by exactly one entry" in failed
    assert "reviewer approved the final code" in failed


def test_agent_commit_to_protected_path_is_detected(repo):
    ref, _ = start(repo)
    write(repo / "tests" / "invariants" / "test_inv.py", "# weakened\n")
    sha = gitutil.commit_all_except_factory(repo, "forged agent commit")
    entry = ledger.append(ref.dir, task=ref.task_id, role="implementer",
                          actor=Actor(kind="agent", id="x", runtime="x", model="x"), on_behalf_of="alice",
                          commits=[sha], started_at="t", ended_at="t")
    core._commit_ledger(ref, entry, [])
    assert "agents did not touch protected paths" in failing(verify(repo, ref.task_id))


def test_change_after_review_needs_a_new_review(repo):
    ref = happy_path(repo)
    write(repo / "orders" / "order.py", "VALUE = 7\n")
    core.record_human(ref, "late tweak")
    failed = failing(verify(repo, ref.task_id))
    assert failed == {"roles ran in the required order", "reviewer approved the final code"} or \
        failed == {"reviewer approved the final code"}


def test_missing_review_fails(repo):
    ref, rt = start(repo)
    core.run_implementer(ref, rt)
    assert "reviewer approved the final code" in failing(verify(repo, ref.task_id))


def test_approval_must_come_from_someone_else(repo):
    ref = happy_path(repo)
    assert "independent human approval" in failing(verify(repo, ref.task_id, approvers=["alice"]))
    assert "independent human approval" in failing(verify(repo, ref.task_id, approvers=[]))
    assert verify(repo, ref.task_id, approvers=["bob"]).ok
```

**Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/factory/test_verify.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.verify'`

**Step 3: Implement `factory/verify.py`**

```python
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
    excluded = {task.initiator} | {e.actor.id for e in entries if e.role == "plan_approval"}
    if any(a not in excluded for a in approvers):
        return []
    errors = [f"{a} cannot approve: initiator or plan approver" for a in approvers]
    return errors + ["needs approval from a human who is neither the initiator nor the plan approver"]
```

**Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/factory -q`
Expected: all pass. If `test_change_after_review_needs_a_new_review` fails, print `failing(...)`. The `record_human` entry is allowed after an approved review, so only "reviewer approved the final code" should fail. Tighten the assertion to that single name once confirmed.

**Step 5: Commit**

```bash
git add factory/verify.py tests/factory/test_verify.py
git commit -q -m "feat(factory): verify chain, custody, commit claims, protected paths, review, approvals

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Status, PR body and the `factory` CLI

**Files:**
- Create: `factory/report.py`, `factory/cli.py`
- Test: `tests/factory/test_cli.py`

**Step 1: Write the failing CLI test (full flow through the CLI with a fake runtime)**

`tests/factory/test_cli.py`:
```python
import json

from typer.testing import CliRunner

from factory.cli import app

from .helpers import HANDOFF, PLAN, REVIEW_OK, block

runner = CliRunner()


def make_fake_dir(path):
    path.mkdir()
    (path / "planner-1.md").write_text(block(PLAN), encoding="utf-8")
    (path / "implementer-1.md").write_text(block(HANDOFF), encoding="utf-8")
    files = path / "implementer-1.files" / "orders"
    files.mkdir(parents=True)
    (files / "order.py").write_text("VALUE = 2\n", encoding="utf-8")
    (path / "reviewer-1.md").write_text(block(REVIEW_OK), encoding="utf-8")


def invoke(*args):
    result = runner.invoke(app, list(args))
    return result.exit_code, result.output


def test_full_flow_through_cli(repo, tmp_path, monkeypatch):
    make_fake_dir(tmp_path / "fake")
    monkeypatch.chdir(repo)
    monkeypatch.setenv("FACTORY_RUNTIME", "fake")
    monkeypatch.setenv("FACTORY_FAKE_DIR", str(tmp_path / "fake"))

    assert invoke("new", "Cancel partial fills", "--goal", "Allow cancel", "--id", "T-001")[0] == 0
    assert invoke("run", "planner")[0] == 0
    code, out = invoke("run", "reviewer")
    assert code == 1 and "cannot do 'reviewer' now" in out
    assert invoke("approve-plan")[0] == 0
    assert invoke("run", "implementer")[0] == 0
    code, out = invoke("run", "reviewer")
    assert code == 0, out
    code, out = invoke("status")
    assert "ready for PR" in out
    code, out = invoke("verify")
    assert code == 0 and "RESULT: PASS" in out
    code, out = invoke("verify", "--check-approvals", "--approver", "alice")
    assert code == 1 and "independent human approval" in out
    code, out = invoke("pr-body")
    assert "Accountable author (initiator):** `alice`" in out
```

**Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/factory/test_cli.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.cli'`

**Step 3: Implement `factory/report.py`**

```python
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
```

**Step 4: Implement `factory/cli.py`**

```python
"""The `factory` command line."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

import typer

from . import core, gitutil
from .errors import FactoryError
from .report import open_pr, pr_body, status_text
from .runtime import get_runtime
from .verify import verify as run_verify

app = typer.Typer(help="Software factory: typed, ledgered hand-offs between agent and human roles.",
                  no_args_is_help=True, add_completion=False)
AGENT_RUNNERS = {"planner": core.run_planner, "implementer": core.run_implementer, "reviewer": core.run_reviewer}
TASK_HELP = "Task id. Defaults to the current factory/<id> branch."


def _guard(action: Callable[[], None]) -> None:
    try:
        action()
    except FactoryError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)


def _repo() -> Path:
    return gitutil.repo_root(Path.cwd())


def _ref(task: Optional[str]) -> core.TaskRef:
    repo = _repo()
    if task:
        return core.TaskRef(repo, task)
    branch = gitutil.current_branch(repo)
    if branch.startswith("factory/"):
        return core.TaskRef(repo, branch.removeprefix("factory/"))
    raise FactoryError("not on a factory/<task> branch; pass --task")


@app.command()
def new(title: str = typer.Argument(..., help="Short task title"),
        goal: str = typer.Option(..., "--goal", "-g", help="What done looks like"),
        task_id: Optional[str] = typer.Option(None, "--id", help="Task id, e.g. T-001"),
        protect: Optional[List[str]] = typer.Option(None, "--protect", help="Glob agents may not change")):
    """Start a task: new branch, task.json, initiator entry."""
    def action():
        ref = core.new_task(_repo(), title, goal, task_id=task_id, protected_paths=protect or None)
        typer.echo(f"created {ref.task_id} on branch factory/{ref.task_id}\nnext: factory run planner")
    _guard(action)


@app.command()
def run(role: str = typer.Argument(..., help="planner | implementer | reviewer"),
        task: Optional[str] = typer.Option(None, "--task", "-t", help=TASK_HELP),
        runtime: Optional[str] = typer.Option(None, "--runtime", help="claude (default) or fake"),
        model: Optional[str] = typer.Option(None, "--model", help="Model alias for the claude runtime")):
    """Run one agent role and record its hand-off."""
    def action():
        if role not in AGENT_RUNNERS:
            raise FactoryError(f"unknown role {role!r}; choose from {', '.join(AGENT_RUNNERS)}")
        ref = _ref(task)
        typer.echo(f"running {role} for {ref.task_id} ...")
        entry = AGENT_RUNNERS[role](ref, get_runtime(runtime, model))
        typer.echo(f"recorded ledger #{entry.seq} {entry.role} ({entry.actor.model}), cost ${entry.cost_usd:.2f}\n")
        typer.echo(status_text(ref))
    _guard(action)


@app.command("approve-plan")
def approve_plan(task: Optional[str] = typer.Option(None, "--task", "-t", help=TASK_HELP),
                 note: Optional[str] = typer.Option(None, "--note", "-m")):
    """Human gate: approve (optionally after editing) plan.md."""
    def action():
        ref = _ref(task)
        entry = core.approve_plan(ref, note=note)
        typer.echo(f"plan approved by {entry.actor.id} (ledger #{entry.seq})\nnext: factory run implementer")
    _guard(action)


@app.command()
def record(message: str = typer.Option(..., "--message", "-m", help="What you changed and why"),
           task: Optional[str] = typer.Option(None, "--task", "-t", help=TASK_HELP)):
    """Commit your own uncommitted edits as a recorded human change."""
    def action():
        entry = core.record_human(_ref(task), message)
        typer.echo(f"recorded human change by {entry.actor.id} (ledger #{entry.seq}); the reviewer must run again")
    _guard(action)


@app.command()
def status(task: Optional[str] = typer.Option(None, "--task", "-t", help=TASK_HELP)):
    """Show task state, ledger and cost."""
    _guard(lambda: typer.echo(status_text(_ref(task))))


@app.command()
def verify(task: Optional[str] = typer.Option(None, "--task", "-t", help=TASK_HELP),
           approver: Optional[List[str]] = typer.Option(None, "--approver", help="PR approver login (repeatable)"),
           check_approvals: bool = typer.Option(False, "--check-approvals", help="Require an independent approval")):
    """Check the ledger against git. Exit 1 on any failure."""
    def action():
        ref = _ref(task)
        report = run_verify(ref.repo, ref.task_id, approvers=(approver or []) if check_approvals else None)
        typer.echo(report.render())
        if not report.ok:
            raise typer.Exit(1)
    _guard(action)


@app.command("pr-body")
def pr_body_cmd(task: Optional[str] = typer.Option(None, "--task", "-t", help=TASK_HELP)):
    """Print the provenance PR body."""
    _guard(lambda: typer.echo(pr_body(_ref(task))))


@app.command()
def pr(task: Optional[str] = typer.Option(None, "--task", "-t", help=TASK_HELP),
       base: str = typer.Option("main", "--base")):
    """Verify, push the task branch and open a GitHub PR with the provenance body."""
    _guard(lambda: typer.echo(open_pr(_ref(task), base=base)))
```

**Step 5: Run all tests**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass. The CLI test runs the real `run_tests` in the temp repo, which costs about 1–2 s for a nested pytest.

**Step 6: Smoke-test the entry point**

Run: `.venv/Scripts/factory --help`
Expected: help text listing `new, run, approve-plan, record, status, verify, pr-body, pr`

**Step 7: Commit**

```bash
git add factory/report.py factory/cli.py tests/factory/test_cli.py
git commit -q -m "feat(factory): CLI, status view, provenance PR body

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: GitHub Action — verify, approvals, tests, gitleaks

**Files:**
- Create: `.github/workflows/factory-verify.yml`

**Step 1: Write the workflow**

```yaml
name: factory-verify

on:
  pull_request:
    types: [opened, synchronize, reopened]
  pull_request_review:
    types: [submitted, dismissed]

permissions:
  contents: read
  pull-requests: read

jobs:
  verify:
    name: verify
    if: startsWith(github.event.pull_request.head.ref, 'factory/')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -q -e ".[dev]"
      - name: Collect current approvals (latest review per user)
        id: approvals
        env:
          GH_TOKEN: ${{ github.token }}
          PR: ${{ github.event.pull_request.number }}
          REPO: ${{ github.repository }}
        run: |
          args=""
          for login in $(gh api "repos/$REPO/pulls/$PR/reviews" --paginate \
              --jq 'group_by(.user.login) | map(last) | .[] | select(.state=="APPROVED") | .user.login'); do
            args="$args --approver $login"
          done
          echo "args=$args" >> "$GITHUB_OUTPUT"
      - name: factory verify
        env:
          HEAD_REF: ${{ github.event.pull_request.head.ref }}
          APPROVER_ARGS: ${{ steps.approvals.outputs.args }}
        run: factory verify --task "${HEAD_REF#factory/}" --check-approvals $APPROVER_ARGS
      - name: tests
        run: python -m pytest -q

  secrets:
    name: secrets
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Note: `--paginate` with `group_by` works per page. That's fine for a demo, and the limit goes in PROTOCOL.md.

**Step 2: Lint the YAML locally**

Run: `.venv/Scripts/python -c "import yaml" 2>/dev/null || .venv/Scripts/python -m pip install -q pyyaml; .venv/Scripts/python -c "import yaml; yaml.safe_load(open('.github/workflows/factory-verify.yml')); print('yaml ok')"`
Expected: `yaml ok`

**Step 3: Commit**

```bash
git add .github/workflows/factory-verify.yml
git commit -q -m "ci: factory-verify with PR approvals, tests and gitleaks

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Demo fixtures (fake runtime) and dry run on the real repo

**Files:**
- Create: `demo/fake/planner-1.md`, `demo/fake/implementer-1.md`, `demo/fake/implementer-1.files/orders/order.py`, `demo/fake/implementer-2.md`, `demo/fake/implementer-2.files/tests/orders/test_order.py`, `demo/fake/reviewer-1.md`, `demo/README.md`

**Step 1: Write the fixtures**

`demo/fake/planner-1.md`: a short realistic message ending with this block:
```json
{"summary": "Let cancel() accept PARTIALLY_FILLED orders and cancel only the remaining quantity; filled quantity is unchanged.",
 "steps": ["In orders/order.py, allow cancel() from NEW and PARTIALLY_FILLED", "Keep FILLED and CANCELLED terminal", "Add behaviour tests in tests/orders/test_order.py"],
 "invariants_affected": ["cancel never changes filled quantity", "FILLED and CANCELLED are terminal", "a rejected operation does not mutate the order"],
 "test_plan": ["partial fill then cancel keeps filled and sets CANCELLED", "cancel of a FILLED order is rejected"],
 "risks": ["Downstream consumers may assume CANCELLED implies filled == 0"]}
```

`demo/fake/implementer-1.files/orders/order.py`: a copy of `orders/order.py` with `cancel()` replaced by:
```python
    def cancel(self) -> None:
        if self.state not in (OrderState.NEW, OrderState.PARTIALLY_FILLED):
            raise OrderError(f"cannot cancel order in state {self.state.value}")
        self.state = OrderState.CANCELLED
```

`demo/fake/implementer-1.md` ends with:
```json
{"summary": "cancel() now accepts partially filled orders; tests not yet written.", "done": ["Relaxed state check in cancel()"], "remaining": ["Add behaviour tests for partial cancel and cancel of FILLED"], "open_questions": [], "files_touched": ["orders/order.py"], "tests": "not_run", "status": "in_progress"}
```

`demo/fake/implementer-2.files/tests/orders/test_order.py`: a copy of `tests/orders/test_order.py` with these appended:
```python


def test_cancel_partially_filled_order_keeps_filled_quantity():
    order = Order("o-7", Side.BUY, Decimal("10"))
    order.fill(Decimal("4"))
    order.cancel()
    assert order.state is OrderState.CANCELLED
    assert order.filled == Decimal("4")


def test_cannot_cancel_filled_order():
    order = Order("o-8", Side.BUY, Decimal("2"))
    order.fill(Decimal("2"))
    with pytest.raises(OrderError):
        order.cancel()
```

`demo/fake/implementer-2.md` ends with:
```json
{"summary": "Added behaviour tests for partial cancel and FILLED cancel; full suite passes.", "done": ["Tests for partial cancel", "Test that FILLED cannot be cancelled"], "remaining": [], "open_questions": [], "files_touched": ["tests/orders/test_order.py"], "tests": "passing", "status": "complete"}
```

`demo/fake/reviewer-1.md` ends with:
```json
{"verdict": "approved", "summary": "Change matches the plan; cancel keeps filled quantity; FILLED stays terminal; tests cover both paths.", "findings": [{"severity": "minor", "file": "orders/order.py", "line": null, "message": "Consider exposing cancelled quantity for downstream reconciliation."}], "invariants_checked": ["cancel never changes filled quantity", "FILLED and CANCELLED are terminal", "rejected operations do not mutate"]}
```

**Step 2: Write `demo/README.md` (the demo script)**

```markdown
# Demo script

Prereqs: venv active (`source .venv/Scripts/activate`), clean `main`, `FACTORY_USER=<your GitHub login>`.

Live (Claude Code):

    factory new "Cancel remaining quantity of partially filled orders" \
      --goal "A partially filled order can be cancelled; filled quantity is kept; FILLED stays terminal." --id T-001
    factory run planner
    cat .factory/tasks/T-001/plan.md        # human reads, may edit
    factory approve-plan
    factory run implementer                 # session 1, may stop with status in_progress
    factory run implementer                 # session 2 resumes from handoff-001.json
    factory run reviewer                    # blind: diff + plan + factory test run
    factory status
    factory verify
    factory pr                              # pushes branch, opens PR with provenance body

Fallback (no network/API): `export FACTORY_RUNTIME=fake FACTORY_FAKE_DIR=demo/fake` and run the same commands.

Tamper demo (after `factory verify` passes):

    echo "- extra scope" >> .factory/tasks/T-001/plan.md && git commit -qam "edit plan"
    factory verify                          # FAIL: chain of custody
    git reset -q --hard HEAD~1
```

**Step 3: Dry run with the fake runtime in a scratch clone (keeps `main` clean)**

Run:
```bash
SCRATCH="C:/Users/miro8/AppData/Local/Temp/claude/b9e1c3dfad8e4268/7682d8c8-1a67-423c-9cf0-41309a06e0b2/scratchpad/dry"
rm -rf "$SCRATCH" && git clone -q . "$SCRATCH" && cd "$SCRATCH"
git config core.autocrlf false
export FACTORY_USER=demo-user FACTORY_RUNTIME=fake FACTORY_FAKE_DIR="$PWD/demo/fake"
F=/c/Users/miro8/case/.venv/Scripts/factory
$F new "Cancel remaining quantity of partially filled orders" --goal "Partial cancel keeps filled" --id T-001
$F run planner && $F approve-plan && $F run implementer && $F run implementer && $F run reviewer
$F verify && $F pr-body
```
Expected: every step succeeds, `RESULT: PASS`, and the PR body shows 7 ledger rows (initiator, planner, plan_approval, implementer ×2, reviewer). The reviewer step runs the real test suite against the patched orders module, so the invariant tests must pass.

**Step 4: Commit**

```bash
cd /c/Users/miro8/case
git add demo
git commit -q -m "demo: fake-runtime fixtures and demo script

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 16: Live run with Claude Code (manual, with the user)

**Step 1: Confirm auth.** Ask the user to run `claude` once and log in, because the OAuth session had expired. Then check:
```bash
echo "Reply OK" | claude -p --output-format json --model haiku --setting-sources project --strict-mcp-config --no-session-persistence | .venv/Scripts/python -c "import sys,json; d=json.load(sys.stdin); print(d['is_error'], d['result'][:20])"
```
Expected: `False OK`

**Step 2: Run the live flow in a scratch clone first** (same commands as Task 15 Step 3, but without the `FACTORY_RUNTIME`/`FACTORY_FAKE_DIR` exports, and with `--model sonnet`). Watch for:
- an agent's final message without a JSON block. If it happens, tighten the role prompt.
- tool denials in the ledger `note`. Adjust policies if a legitimate tool is denied.
- the Windows `claude` executable resolution in `ClaudeRuntime.run`.

**Step 3: Record findings** in `BUILD_LOG.md` ("what went wrong"). If the role prompts changed, commit them:
```bash
git add .factory/roles BUILD_LOG.md
git commit -q -m "tune role prompts after first live run

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 17: Publish to GitHub, open the PR, branch protection (manual — confirm with the user first)

These steps publish code and change repo settings. **Ask the user before each one.**

**Step 1:** Create the public repo and push `main` (the user picks the name):
```bash
gh repo create <name> --public --source . --remote origin --push
```

**Step 2:** Branch protection on `main`: require the `verify` and `secrets` checks plus 1 approval, and enforce it for admins:
```bash
gh api -X PUT "repos/<owner>/<name>/branches/main/protection" --input - <<'EOF'
{"required_status_checks":{"strict":true,"contexts":["verify","secrets"]},
 "enforce_admins":true,
 "required_pull_request_reviews":{"required_approving_review_count":1},
 "restrictions":null}
EOF
```

**Step 3:** Run the live flow on the real repo (Task 15 demo script), then `factory pr`. Expected: PR opened. The `verify` check fails with "needs approval from a human who is neither the initiator nor the plan approver". That failure is the intended demo state. A second account (or a colleague) approving flips it to green.

**Step 4:** Screenshot the PR body and the failing/passing check for the presentation.

---

### Task 18 (stretch): Reviewer eval — does the blind reviewer catch seeded invariant bugs?

**Files:**
- Create: `evals/__init__.py` (empty), `evals/reviewer_eval.py`
- Test: `tests/factory/test_eval_cases.py`

**Step 1: Write the failing test (anchors apply to the current code, no model calls)**

`tests/factory/test_eval_cases.py`:
```python
from evals.reviewer_eval import CASES, apply_edits


def test_every_case_applies_cleanly():
    for case in CASES:
        patched = apply_edits(case)
        assert patched, case.name
```

**Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/factory/test_eval_cases.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'evals'`

**Step 3: Implement `evals/reviewer_eval.py`**

```python
"""Reviewer eval: does the blind reviewer role catch seeded invariant bugs?

Usage: python -m evals.reviewer_eval [--runtime claude] [--model sonnet]
Each case patches a temp copy of the repo and asks the reviewer for a verdict.
Bug cases should get changes_requested; the control case should be approved.
"""
from __future__ import annotations

import argparse
import difflib
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from factory.errors import FactoryError
from factory.prompts import build_prompt, policy_for, role_prompt_path
from factory.runtime import extract_json_block, get_runtime
from factory.schemas import Review, Task

ROOT = Path(__file__).resolve().parents[1]
ORDER = "orders/order.py"
TESTS = "tests/orders/test_order.py"
GOAL = "Allow cancelling the remaining quantity of a partially filled order. Filled quantity is kept."

CONTROL = [
    (ORDER, "        if self.state is not OrderState.NEW:\n            raise OrderError(f\"cannot cancel",
     "        if self.state not in (OrderState.NEW, OrderState.PARTIALLY_FILLED):\n"
     "            raise OrderError(f\"cannot cancel"),
    (TESTS, "", "\n\ndef test_cancel_partially_filled_order_keeps_filled_quantity():\n"
                "    order = Order(\"o-9\", Side.BUY, Decimal(\"10\"))\n    order.fill(Decimal(\"4\"))\n"
                "    order.cancel()\n    assert order.state is OrderState.CANCELLED\n"
                "    assert order.filled == Decimal(\"4\")\n"),
]


@dataclass
class Case:
    name: str
    edits: list[tuple[str, str, str]]  # (path, old, new); old == "" appends
    expect: str


CASES = [
    Case("control-correct-change", CONTROL, "approved"),
    Case("cancel-allowed-from-filled", CONTROL + [
        (ORDER, "(OrderState.NEW, OrderState.PARTIALLY_FILLED):\n            raise OrderError(f\"cannot cancel",
         "(OrderState.NEW, OrderState.PARTIALLY_FILLED, OrderState.FILLED):\n"
         "            raise OrderError(f\"cannot cancel")], "changes_requested"),
    Case("cancel-resets-filled", CONTROL + [
        (ORDER, "        self.state = OrderState.CANCELLED\n",
         "        self.filled = Decimal(\"0\")\n        self.state = OrderState.CANCELLED\n")], "changes_requested"),
    Case("overfill-check-per-fill-only", CONTROL + [
        (ORDER, "if self.filled + qty > self.quantity:", "if qty > self.quantity:")], "changes_requested"),
    Case("mutate-before-validate", CONTROL + [
        (ORDER, "        if self.filled + qty > self.quantity:\n            raise OrderError(\"fill would exceed order "
                "quantity\")\n        self.filled += qty\n",
         "        self.filled += qty\n        if self.filled > self.quantity:\n            raise OrderError(\"fill "
         "would exceed order quantity\")\n")], "changes_requested"),
]


def apply_edits(case: Case) -> dict[str, tuple[str, str]]:
    """Return {path: (original, patched)} for every file the case touches."""
    files: dict[str, tuple[str, str]] = {}
    for path, old, new in case.edits:
        original = (ROOT / path).read_text(encoding="utf-8")
        current = files.get(path, (original, original))[1]
        if old == "":
            patched = current + new
        elif old in current:
            patched = current.replace(old, new, 1)
        else:
            raise ValueError(f"{case.name}: anchor not found in {path}")
        files[path] = (original, patched)
    return files


def run_case(case: Case, runtime) -> tuple[str, str]:
    files = apply_edits(case)
    diff = "".join("".join(difflib.unified_diff(o.splitlines(True), p.splitlines(True), f"a/{path}", f"b/{path}"))
                   for path, (o, p) in files.items())
    task = Task(id="T-eval", title="Cancel partial fills", goal=GOAL, initiator="eval", base_commit="0" * 40,
                branch="factory/T-eval", created_at="2026-01-01T00:00:00Z")
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for part in ("orders", "tests", ".factory/roles", "AGENTS.md", "CLAUDE.md", "pyproject.toml"):
            src, dst = ROOT / part, work / part
            if src.is_dir():
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", ".hypothesis"))
            elif src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        for path, (_, patched) in files.items():
            (work / path).write_text(patched, encoding="utf-8", newline="\n")
        prompt = build_prompt(role_prompt_path(ROOT, "reviewer").read_text(encoding="utf-8"), [
            ("Task", task.model_dump_json(indent=2)),
            ("Diff under review", f"```diff\n{diff}\n```"),
            ("Test run by the factory", "Not run for this eval. You may run the tests yourself."),
        ], Review)
        try:
            result = runtime.run(role="reviewer", prompt=prompt, policy=policy_for("reviewer", task),
                                 cwd=work, attempt=0)
            review = Review.model_validate(extract_json_block(result.text))
        except (FactoryError, ValueError) as exc:
            return "error", str(exc)[:120]
    return review.verdict, f"${result.cost_usd:.2f} {review.summary[:80]}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", default="claude")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    runtime = get_runtime(args.runtime, args.model)
    rows, correct = [], 0
    for case in CASES:
        got, detail = run_case(case, runtime)
        ok = got == case.expect
        correct += ok
        rows.append(f"| {case.name} | {case.expect} | {got} | {'yes' if ok else 'NO'} | {detail} |")
        print(rows[-1], flush=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    report = "\n".join([f"# Reviewer eval ({stamp}, model: {args.model or 'default'})", "",
                        "| case | expected | got | correct | detail |", "|---|---|---|---|---|", *rows, "",
                        f"Score: {correct}/{len(CASES)}", ""])
    out = ROOT / "evals" / "results" / "latest.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8", newline="\n")
    print(f"\nScore: {correct}/{len(CASES)} -> {out}")


if __name__ == "__main__":
    main()
```

**Step 4: Run the test**

Run: `.venv/Scripts/python -m pytest tests/factory/test_eval_cases.py -q`
Expected: `1 passed`

**Step 5: Run the eval live** (costs API money, so confirm with the user first):
`.venv/Scripts/python -m evals.reviewer_eval --model sonnet`
Expected: a score printed and `evals/results/latest.md` written. Record the score honestly in BUILD_LOG.md and the presentation, whatever it is.

**Step 6: Commit**

```bash
git add evals tests/factory/test_eval_cases.py
git commit -q -m "eval: reviewer catch-rate on seeded invariant bugs

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 19: Docs — PROTOCOL.md, README, build log, presentation

**Files:**
- Create: `spec/PROTOCOL.md`, `README.md`, `docs/presentation.md`
- Modify: `BUILD_LOG.md`

**Step 1: `spec/PROTOCOL.md`** covers the contract, in this order:
1. Roles and who may fill them: agent roles = planner, implementer, reviewer; human roles = initiator, plan_approval, human_change.
2. Task folder layout: `task.json`, `plan.md`, `handoff-NNN.json`, `review-NNN.json`, `ledger.jsonl`.
3. Ledger entry fields (link `ledger-entry.schema.json`), plus the hash rule: `sha256(canonical JSON without "hash")` with sorted keys and `(",", ":")` separators, and `prev_hash` chaining from 64 zeros.
4. Commit rules: code commits are claimed by exactly one entry; ledger commits touch only the task folder; no merge commits on task branches; trailers `Factory-Task`, `Factory-Entry`, `Factory-Role` and `Co-authored-by` for agents.
5. Role order (the `allowed_next` table).
6. The verify checks (the list from the design doc §6).
7. Authorship: the initiator is the accountable author; agents are contributors; the approver must be someone else.
8. Limits: tamper-evident, not tamper-proof; self-reported model identity; reviewer independence relies on prompt and tool policy; squash or rebase invalidates commit claims; review pagination; identity is `FACTORY_USER`/gh login and unsigned.
9. Roadmap: one signed in-toto statement per ledger entry (sigstore/gitsign), with verify checking signatures against an identity policy.

**Step 2: `README.md`**: one-paragraph pitch, quickstart (install, demo commands from `demo/README.md`), repo map, and links to the design doc, PROTOCOL.md, BUILD_LOG.md and the presentation.

**Step 3: `docs/presentation.md`**, a structured doc for 35–40 min:
1. Definition (deep, 4 min): "a contract, not a pipeline"; where it sits on the range; what it is not.
2. People and problems (3 min): a table of the 7 people, the problem each has, what the factory does for them now / later / never.
3. Design and walkthrough (deep, 8 min): the diagram, the T-001 walkthrough, where humans step in.
4. **Live demo (10 min)**: the demo script, then the tamper demo, then the PR with its failing approval check.
5. Provenance deep-dive (deep, 6 min): ledger entry, the authorship answer, the verify checks, honest limits, the in-toto roadmap.
6. Delegate / review / own (2 min):
   - Delegate: planning drafts, implementation, first-pass review.
   - Review: plan and PR.
   - Own: invariants, approval, merge and deploy, role prompts.
7. Quality and security (deep, 3 min): blind reviewer, factory-run tests, protected invariants, gitleaks, the reviewer eval score.
8. Non-engineers (1 min): same protocol plus an approved template repo; an engineer is the plan approver; runs only in the group's platform. Sketch only.
9. Adoption (2 min):
   - Win the senior engineer by making the invariants theirs: protected paths plus the plan gate.
   - Give the early adopter a measurable bar (ledger cost and loop counts).
   - Give team leads shared role prompts in the repo.
10. First 90 days (1 min):
    - 0–30: pilot with 2 volunteer teams, one per company.
    - 30–60: signing, plus an MCP/IDE front-end.
    - 60–90: non-engineer path, plus metrics from the ledger.
    - What I expect to learn: plan-gate value, reviewer catch rate, cost per change.
11. Build log and time spent (1 min).

**Step 4: Update `BUILD_LOG.md`** with real times per task, what was delegated, reviewed and hand-written, what went wrong, and the total time and why.

**Step 5: Run the full suite one last time**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass

**Step 6: Commit**

```bash
git add spec/PROTOCOL.md README.md docs/presentation.md BUILD_LOG.md
git commit -q -m "docs: protocol spec, README, presentation, build log

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Step 7: Record a screen capture** of the Task 15 demo script (live and fake) as the backup the case study requires. This is manual.
