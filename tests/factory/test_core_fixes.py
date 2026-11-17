import subprocess

import pytest

from factory import core, gitutil
from factory.errors import FactoryError

from .helpers import fake


def _branch(repo):
    return gitutil.git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()


def test_new_task_invalid_id_leaves_no_branch_or_dir(repo):
    before = _branch(repo)
    with pytest.raises(FactoryError):
        core.new_task(repo, "t", "g", task_id="foo")
    assert _branch(repo) == before
    assert not (repo / ".factory" / "tasks" / "foo").exists()


def test_resolve_user_has_no_git_user_name_fallback(repo, monkeypatch):
    monkeypatch.delenv("FACTORY_USER", raising=False)

    def no_gh(*args, **kwargs):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(core.subprocess, "run", no_gh)
    with pytest.raises(FactoryError):
        core.resolve_user(repo)


def test_approve_plan_normalises_crlf(repo):
    ref = core.new_task(repo, "t", "g", task_id="T-001")
    core.run_planner(ref, fake())
    plan = ref.path("plan.md")
    plan.write_bytes(plan.read_bytes().replace(b"\n", b"\r\n"))
    entry = core.approve_plan(ref)
    assert b"\r" not in plan.read_bytes()
    assert "edited" not in (entry.note or "")


def test_load_task_corrupt_json_is_factory_error(repo):
    ref = core.new_task(repo, "t", "g", task_id="T-001")
    ref.path("task.json").write_bytes(b"\xff\xfe garbage")
    with pytest.raises(FactoryError):
        core.load_task(ref)
    ref.path("task.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(FactoryError):
        core.load_task(ref)
