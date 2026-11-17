import subprocess

import pytest


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A small git repo shaped like this one: orders/, protected tests/invariants/, role prompts."""
    empty_config = tmp_path / "empty.gitconfig"
    empty_config.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty_config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    for key, value in [("user.name", "Alice"), ("user.email", "alice@example.com"),
                       ("core.autocrlf", "false"), ("commit.gpgsign", "false")]:
        git(r, "config", key, value)
    write(r / ".gitattributes", "* text=auto eol=lf\n")
    write(r / ".gitignore", "__pycache__/\n.pytest_cache/\n.hypothesis/\n")
    write(r / "orders" / "order.py", "VALUE = 1\n")
    write(r / "tests" / "invariants" / "test_inv.py", "def test_ok():\n    assert True\n")
    for role in ("planner", "implementer", "reviewer"):
        write(r / ".factory" / "roles" / f"{role}.md", f"You are the {role}.\n")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "init")
    monkeypatch.setenv("FACTORY_USER", "alice")
    return r
