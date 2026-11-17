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
