from factory import core, ledger
from factory.runtime import FakeStep
from factory.schemas import Review

from .helpers import REVIEW_NO, RecordingRuntime, block, fake, start, runner_fail, runner_pass


def test_reviewer_sees_diff_but_not_implementer_notes(repo):
    rt = RecordingRuntime(fake().steps)
    ref, _ = start(repo, rt)
    core.run_implementer(ref, rt)
    entry = core.run_reviewer(ref, rt, test_runner=runner_pass)
    prompt = [p for role, p in rt.prompts if role == "reviewer"][0]
    assert "VALUE = 2" in prompt
    assert "Implemented partial cancel" not in prompt
    assert entry.outputs.keys() == {"review-001.json"}
    assert entry.note.startswith("factory test run passed")


def test_failing_tests_override_an_approval(repo):
    ref, rt = start(repo)
    core.run_implementer(ref, rt)
    core.run_reviewer(ref, rt, test_runner=runner_fail)
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
    core.run_reviewer(ref, rt, test_runner=runner_pass)
    core.run_implementer(ref, rt)
    second = [p for role, p in rt.prompts if role == "implementer"][1]
    assert "Reviewer findings to address" in second and "add a test" in second
    assert "review-001.json" in ledger.load(ref.dir)[-1].inputs
