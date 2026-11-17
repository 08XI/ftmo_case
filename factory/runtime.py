"""Agent runtimes. A runtime runs one role once and returns its final message plus usage."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .errors import AgentOutputError, AgentRunError


@dataclass(frozen=True)
class ToolPolicy:
    allowed: tuple[str, ...]
    denied: tuple[str, ...] = ()


@dataclass
class RunResult:
    text: str
    model: str
    runtime: str
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    session_id: str | None = None
    denials: list[str] = field(default_factory=list)


class Runtime(Protocol):
    name: str

    def run(self, *, role: str, prompt: str, policy: ToolPolicy, cwd: Path, attempt: int) -> RunResult: ...


_JSON_BLOCK = re.compile(r"```json[ \t]*\r?\n(.*?)\r?\n```", re.DOTALL)


def extract_json_block(text: str) -> dict:
    blocks = _JSON_BLOCK.findall(text)
    candidate = blocks[-1] if blocks else text.strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise AgentOutputError(f"final message has no valid ```json block: {exc}") from exc
    if not isinstance(value, dict):
        raise AgentOutputError("the ```json block must contain a JSON object")
    return value


def parse_claude_output(stdout: str) -> RunResult:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise AgentRunError(f"claude returned non-JSON output: {stdout[:300]!r}") from exc
    if isinstance(data, list):
        data = next((d for d in reversed(data) if isinstance(d, dict) and d.get("type") == "result"), {})
    if data.get("is_error") or data.get("subtype") != "success":
        raise AgentRunError(f"agent run failed ({data.get('subtype')}): {str(data.get('result', ''))[:500]}")
    usage = data.get("usage") or {}
    model_usage = data.get("modelUsage") or {}
    model = max(model_usage, key=lambda m: model_usage[m].get("costUSD", 0)) if model_usage else "unknown"
    tokens_in = sum(int(usage.get(k) or 0)
                    for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    denials = [str(d.get("tool_name")) if isinstance(d, dict) else str(d)
               for d in data.get("permission_denials") or []]
    return RunResult(
        text=str(data.get("result", "")), model=model, runtime="claude-code",
        cost_usd=float(data.get("total_cost_usd") or 0), tokens_in=tokens_in,
        tokens_out=int(usage.get("output_tokens") or 0), session_id=data.get("session_id"), denials=denials,
    )


class ClaudeRuntime:
    """Runs a role as headless Claude Code, isolated from the user's personal settings and MCP servers."""

    name = "claude-code"

    def __init__(self, model: str | None = None, executable: str = "claude", timeout_s: int = 1800):
        self.model = model
        self.executable = executable
        self.timeout_s = timeout_s

    def command(self, policy: ToolPolicy) -> list[str]:
        cmd = [self.executable, "-p", "--output-format", "json", "--permission-mode", "default",
               "--setting-sources", "project", "--strict-mcp-config", "--no-session-persistence"]
        if self.model:
            cmd += ["--model", self.model]
        cmd += ["--allowedTools", *policy.allowed]
        if policy.denied:
            cmd += ["--disallowedTools", *policy.denied]
        return cmd

    def run(self, *, role: str, prompt: str, policy: ToolPolicy, cwd: Path, attempt: int) -> RunResult:
        exe = shutil.which(self.executable)
        if exe is None:
            raise AgentRunError(f"'{self.executable}' not found on PATH; install Claude Code or use --runtime fake")
        cmd = self.command(policy)
        cmd[0] = exe
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace", cwd=cwd)
        try:
            stdout, stderr = proc.communicate(input=prompt, timeout=self.timeout_s)
        except subprocess.TimeoutExpired as exc:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
            else:
                proc.kill()
            proc.communicate()
            raise AgentRunError(f"{role} timed out after {self.timeout_s}s") from exc
        if not stdout.strip():
            raise AgentRunError(f"{role} produced no output (exit {proc.returncode}): {stderr.strip()[:500]}")
        return parse_claude_output(stdout)


@dataclass
class FakeStep:
    text: str
    files: dict[str, str] = field(default_factory=dict)
    model: str = "fake-model"
    cost_usd: float = 0.0
    error: str | None = None


class FakeRuntime:
    """Deterministic runtime: replays scripted final messages and file writes. Used by tests and as demo fallback."""

    name = "fake"

    def __init__(self, steps: dict[str, list[FakeStep]]):
        self.steps = steps

    def run(self, *, role: str, prompt: str, policy: ToolPolicy, cwd: Path, attempt: int) -> RunResult:
        queue = self.steps.get(role, [])
        if attempt >= len(queue):
            raise AgentRunError(f"fake runtime has no step {attempt + 1} for role {role}")
        step = queue[attempt]
        if step.error:
            raise AgentRunError(step.error)
        for rel, content in step.files.items():
            target = Path(cwd) / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        return RunResult(text=step.text, model=step.model, runtime=self.name, cost_usd=step.cost_usd)

    @classmethod
    def from_dir(cls, directory: Path) -> "FakeRuntime":
        """Load <role>-<n>.md final messages and optional <role>-<n>.files/ trees."""
        directory = Path(directory)
        found: dict[str, list[tuple[int, FakeStep]]] = {}
        for md in sorted(directory.glob("*-*.md")):
            m = re.fullmatch(r"(.+)-(\d+)", md.stem)
            if m is None:
                continue
            role, number = m.groups()
            files_dir = directory / f"{md.stem}.files"
            files = {}
            if files_dir.is_dir():
                files = {p.relative_to(files_dir).as_posix(): p.read_text(encoding="utf-8")
                         for p in sorted(files_dir.rglob("*"))
                         if p.is_file() and "__pycache__" not in p.relative_to(files_dir).parts}
            found.setdefault(role, []).append((int(number), FakeStep(md.read_text(encoding="utf-8"), files)))
        return cls({role: [s for _, s in sorted(items, key=lambda t: t[0])] for role, items in found.items()})


def get_runtime(name: str | None = None, model: str | None = None) -> Runtime:
    name = name or os.environ.get("FACTORY_RUNTIME", "claude")
    if name == "claude":
        return ClaudeRuntime(model=model or os.environ.get("FACTORY_MODEL"))
    if name == "fake":
        directory = os.environ.get("FACTORY_FAKE_DIR")
        if not directory:
            raise AgentRunError("FACTORY_FAKE_DIR must point at a directory of fake runs (see demo/fake)")
        return FakeRuntime.from_dir(Path(directory))
    raise AgentRunError(f"unknown runtime {name!r}; use 'claude' or 'fake'")
