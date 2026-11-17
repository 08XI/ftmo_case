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


def runner_pass(repo):
    return True, "1 passed"


def runner_fail(repo):
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
    core.run_reviewer(ref, rt, test_runner=runner_pass)
    return ref
