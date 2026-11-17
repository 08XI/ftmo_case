from factory import gitutil

from .conftest import git, write


def test_changed_paths_lists_modified_and_untracked(repo):
    write(repo / "orders" / "order.py", "VALUE = 2\n")
    write(repo / "orders" / "new" / "deep.py", "x = 1\n")
    assert gitutil.changed_paths(repo) == ["orders/new/deep.py", "orders/order.py"]


def test_commit_all_except_factory_leaves_factory_changes(repo):
    write(repo / "orders" / "order.py", "VALUE = 2\n")
    write(repo / ".factory" / "tasks" / "T-1" / "x.json", "{}\n")
    sha = gitutil.commit_all_except_factory(repo, "code")
    assert gitutil.files_in_commit(repo, sha) == ["orders/order.py"]
    assert gitutil.changed_paths(repo) == [".factory/tasks/T-1/x.json"]


def test_commits_between_and_parents(repo):
    base = gitutil.head(repo)
    write(repo / "a.txt", "a\n")
    first = gitutil.commit_paths(repo, ["a.txt"], "a")
    write(repo / "b.txt", "b\n")
    second = gitutil.commit_paths(repo, ["b.txt"], "b")
    assert gitutil.commits_between(repo, base) == [first, second]
    assert gitutil.parents(repo, second) == [first]
    assert gitutil.is_ancestor(repo, first)
    git(repo, "checkout", "-q", "-b", "other", base)
    assert not gitutil.is_ancestor(repo, second)


def test_diff_excludes_factory(repo):
    base = gitutil.head(repo)
    write(repo / "orders" / "order.py", "VALUE = 3\n")
    write(repo / ".factory" / "tasks" / "T-1" / "x.json", "{}\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "both")
    diff = gitutil.diff(repo, base, "HEAD")
    assert "orders/order.py" in diff
    assert ".factory" not in diff
