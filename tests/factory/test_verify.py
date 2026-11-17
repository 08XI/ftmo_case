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
    # human_change is allowed after an approved review, so only the review check fails
    assert failing(verify(repo, ref.task_id)) == {"reviewer approved the final code"}


def test_missing_review_fails(repo):
    ref, rt = start(repo)
    core.run_implementer(ref, rt)
    assert "reviewer approved the final code" in failing(verify(repo, ref.task_id))


def test_approval_must_come_from_someone_else(repo):
    ref = happy_path(repo)
    assert "independent human approval" in failing(verify(repo, ref.task_id, approvers=["alice"]))
    assert "independent human approval" in failing(verify(repo, ref.task_id, approvers=[]))
    assert verify(repo, ref.task_id, approvers=["bob"]).ok


def test_approval_is_case_insensitive(repo):
    ref = happy_path(repo)
    assert "independent human approval" in failing(verify(repo, ref.task_id, approvers=["ALICE"]))


def test_approvers_are_normalised(repo):
    ref = happy_path(repo)
    for bad in ([""], [" Alice "], ["@alice"]):
        assert "independent human approval" in failing(verify(repo, ref.task_id, approvers=bad)), bad
    assert verify(repo, ref.task_id, approvers=[" bob "]).ok


def test_uncommitted_task_file_is_detected(repo):
    ref = happy_path(repo)
    with ref.path("plan.md").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write("- uncommitted\n")
    assert "task folder is committed" in failing(verify(repo, ref.task_id))


def test_base_commit_must_be_an_ancestor(repo):
    from factory.verify import _base_errors

    ref = happy_path(repo)
    task = core.load_task(ref)
    assert _base_errors(repo, task) == []
    git(repo, "checkout", "-q", "--orphan", "other")
    write(repo / "other.txt", "x\n")
    git(repo, "add", "other.txt")
    git(repo, "commit", "-qm", "orphan")
    orphan = gitutil.git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-qf", task.branch)
    assert _base_errors(repo, task.model_copy(update={"base_commit": orphan}))


def test_forged_reviewed_head_is_rejected(repo):
    from factory import verify as v

    ref = happy_path(repo)
    entries = ledger.load(ref.dir)
    last = entries[-1]
    forged = last.model_copy(update={"inputs": {**last.inputs, "head": "HEAD"}})
    errors = v._review_errors(repo, [*entries[:-1], forged], core.verdict_reader(ref), [])
    assert errors and "not on this branch" in errors[0]


def test_custody_rejects_path_like_names(repo):
    from factory.verify import _custody_errors

    ref = happy_path(repo)
    entries = ledger.load(ref.dir)
    last = entries[-1]
    bad = last.model_copy(update={"outputs": {**last.outputs, "../x": "0" * 64}})
    errors = _custody_errors(ref, [*entries[:-1], bad])
    assert any("../x: invalid file name in ledger" in e for e in errors)
