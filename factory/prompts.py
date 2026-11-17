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
