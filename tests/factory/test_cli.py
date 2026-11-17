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
