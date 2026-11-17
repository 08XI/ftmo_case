"""Thin wrappers over the git CLI. All paths are repo-relative POSIX strings."""
from __future__ import annotations

import subprocess
from pathlib import Path

from .errors import GitError

EXCLUDE_FACTORY = ":(exclude).factory"


def git(repo: Path, *args: str, strip: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip() if strip else proc.stdout


def repo_root(start: Path) -> Path:
    return Path(git(start, "rev-parse", "--show-toplevel"))


def head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD")


def current_branch(repo: Path) -> str:
    return git(repo, "rev-parse", "--abbrev-ref", "HEAD")


def config(repo: Path, key: str) -> str | None:
    try:
        return git(repo, "config", key) or None
    except GitError:
        return None


def changed_paths(repo: Path) -> list[str]:
    """Modified, staged, deleted and untracked (non-ignored) files."""
    out = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all", strip=False)
    parts = out.split("\0")
    paths: list[str] = []
    i = 0
    while i < len(parts):
        item = parts[i]
        if not item:
            i += 1
            continue
        status, path = item[:2], item[3:]
        paths.append(path)
        if status[0] in "RC":
            paths.append(parts[i + 1])
            i += 2
        else:
            i += 1
    return sorted(set(paths))


def commits_between(repo: Path, base: str, tip: str = "HEAD") -> list[str]:
    out = git(repo, "rev-list", "--reverse", f"{base}..{tip}")
    return out.splitlines() if out else []


def parents(repo: Path, sha: str) -> list[str]:
    return git(repo, "rev-list", "--parents", "-n", "1", sha).split()[1:]


def files_in_commit(repo: Path, sha: str) -> list[str]:
    out = git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", "-z", sha, strip=False)
    return [p for p in out.split("\0") if p]


def is_ancestor(repo: Path, ancestor: str, tip: str = "HEAD") -> bool:
    proc = subprocess.run(["git", "merge-base", "--is-ancestor", ancestor, tip], cwd=repo, capture_output=True)
    return proc.returncode == 0


def diff(repo: Path, base: str, tip: str) -> str:
    return git(repo, "diff", base, tip, "--", ".", EXCLUDE_FACTORY, strip=False)


def working_diff(repo: Path) -> str:
    return git(repo, "diff", "HEAD", "--", ".", EXCLUDE_FACTORY, strip=False)


def commit_all_except_factory(repo: Path, message: str) -> str:
    git(repo, "add", "-A", "--", ".", EXCLUDE_FACTORY)
    git(repo, "commit", "-q", "-m", message)
    return head(repo)


def commit_paths(repo: Path, paths: list[str], message: str) -> str:
    git(repo, "add", "--", *paths)
    git(repo, "commit", "-q", "-m", message)
    return head(repo)
