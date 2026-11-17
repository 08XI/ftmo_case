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


def test_denials_include_the_blocked_shell_command():
    stdout = json.dumps({
        "type": "result", "subtype": "success", "is_error": False, "result": "ok",
        "permission_denials": [{"tool_name": "Bash", "tool_input": {"command": "cd x &&\n  python -m pytest"}}],
    })
    assert parse_claude_output(stdout).denials == ["Bash(cd x && python -m pytest)"]


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


def test_fake_runtime_from_dir_skips_stray_files(tmp_path):
    (tmp_path / "planner-1.md").write_text("plan", encoding="utf-8")
    (tmp_path / "notes-draft.md").write_text("stray", encoding="utf-8")
    (tmp_path / "planner-1.files" / "__pycache__").mkdir(parents=True)
    (tmp_path / "planner-1.files" / "__pycache__" / "x.pyc").write_text("junk", encoding="utf-8")
    (tmp_path / "planner-1.files" / "a.txt").write_text("A\n", encoding="utf-8")
    rt = FakeRuntime.from_dir(tmp_path)
    assert list(rt.steps) == ["planner"]
    assert rt.steps["planner"][0].text == "plan"
    assert rt.steps["planner"][0].files == {"a.txt": "A\n"}


def test_claude_runtime_timeout_raises_promptly(tmp_path, monkeypatch):
    import sys
    import time
    sleeper = [sys.executable, "-c", "import time; time.sleep(30)"]
    monkeypatch.setattr(ClaudeRuntime, "command", lambda self, policy: list(sleeper))
    monkeypatch.setattr("factory.runtime.shutil.which", lambda name: sys.executable)
    rt = ClaudeRuntime(executable="claude", timeout_s=1)
    start = time.monotonic()
    with pytest.raises(AgentRunError, match="timed out"):
        rt.run(role="planner", prompt="p", policy=ToolPolicy(()), cwd=tmp_path, attempt=0)
    assert time.monotonic() - start < 15
