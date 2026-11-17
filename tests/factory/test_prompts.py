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
