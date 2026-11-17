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
