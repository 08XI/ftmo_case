"""The `factory` command line."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

import typer

from . import core, gitutil
from .errors import FactoryError
from .report import open_pr, pr_body, status_text
from .runtime import get_runtime
from .verify import verify as run_verify

app = typer.Typer(help="Software factory: typed, ledgered hand-offs between agent and human roles.",
                  no_args_is_help=True, add_completion=False)
AGENT_RUNNERS = {"planner": core.run_planner, "implementer": core.run_implementer, "reviewer": core.run_reviewer}
TASK_HELP = "Task id. Defaults to the current factory/<id> branch."


def _guard(action: Callable[[], None]) -> None:
    try:
        action()
    except FactoryError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    except (ValueError, OSError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)


def _repo() -> Path:
    return gitutil.repo_root(Path.cwd())


def _ref(task: Optional[str]) -> core.TaskRef:
    repo = _repo()
    if task:
        return core.TaskRef(repo, task)
    branch = gitutil.current_branch(repo)
    if branch.startswith("factory/"):
        return core.TaskRef(repo, branch.removeprefix("factory/"))
    raise FactoryError("not on a factory/<task> branch; pass --task")


@app.command()
def new(title: str = typer.Argument(..., help="Short task title"),
        goal: str = typer.Option(..., "--goal", "-g", help="What done looks like"),
        task_id: Optional[str] = typer.Option(None, "--id", help="Task id, e.g. T-001"),
        protect: Optional[List[str]] = typer.Option(None, "--protect", help="Glob agents may not change")):
    """Start a task: new branch, task.json, initiator entry."""
    def action():
        ref = core.new_task(_repo(), title, goal, task_id=task_id, protected_paths=protect or None)
        typer.echo(f"created {ref.task_id} on branch factory/{ref.task_id}\nnext: factory run planner")
    _guard(action)


@app.command()
def run(role: str = typer.Argument(..., help="planner | implementer | reviewer"),
        task: Optional[str] = typer.Option(None, "--task", "-t", help=TASK_HELP),
        runtime: Optional[str] = typer.Option(None, "--runtime", help="claude (default) or fake"),
        model: Optional[str] = typer.Option(None, "--model", help="Model alias for the claude runtime")):
    """Run one agent role and record its hand-off."""
    def action():
        if role not in AGENT_RUNNERS:
            raise FactoryError(f"unknown role {role!r}; choose from {', '.join(AGENT_RUNNERS)}")
        ref = _ref(task)
        typer.echo(f"running {role} for {ref.task_id} ...")
        entry = AGENT_RUNNERS[role](ref, get_runtime(runtime, model))
        typer.echo(f"recorded ledger #{entry.seq} {entry.role} ({entry.actor.model}), cost ${entry.cost_usd:.2f}\n")
        typer.echo(status_text(ref))
    _guard(action)


@app.command("approve-plan")
def approve_plan(task: Optional[str] = typer.Option(None, "--task", "-t", help=TASK_HELP),
                 note: Optional[str] = typer.Option(None, "--note", "-m")):
    """Human gate: approve (optionally after editing) plan.md."""
    def action():
        ref = _ref(task)
        entry = core.approve_plan(ref, note=note)
        typer.echo(f"plan approved by {entry.actor.id} (ledger #{entry.seq})\nnext: factory run implementer")
    _guard(action)


@app.command()
def record(message: str = typer.Option(..., "--message", "-m", help="What you changed and why"),
           task: Optional[str] = typer.Option(None, "--task", "-t", help=TASK_HELP)):
    """Commit your own uncommitted edits as a recorded human change."""
    def action():
        entry = core.record_human(_ref(task), message)
        typer.echo(f"recorded human change by {entry.actor.id} (ledger #{entry.seq}); the reviewer must run again")
    _guard(action)


@app.command()
def status(task: Optional[str] = typer.Option(None, "--task", "-t", help=TASK_HELP)):
    """Show task state, ledger and cost."""
    _guard(lambda: typer.echo(status_text(_ref(task))))


@app.command()
def verify(task: Optional[str] = typer.Option(None, "--task", "-t", help=TASK_HELP),
           approver: Optional[List[str]] = typer.Option(None, "--approver", help="PR approver login (repeatable)"),
           check_approvals: bool = typer.Option(False, "--check-approvals", help="Require an independent approval")):
    """Check the ledger against git. Exit 1 on any failure."""
    def action():
        ref = _ref(task)
        report = run_verify(ref.repo, ref.task_id, approvers=(approver or []) if check_approvals else None)
        typer.echo(report.render())
        if not report.ok:
            raise typer.Exit(1)
    _guard(action)


@app.command("pr-body")
def pr_body_cmd(task: Optional[str] = typer.Option(None, "--task", "-t", help=TASK_HELP)):
    """Print the provenance PR body."""
    _guard(lambda: typer.echo(pr_body(_ref(task))))


@app.command()
def pr(task: Optional[str] = typer.Option(None, "--task", "-t", help=TASK_HELP),
       base: str = typer.Option("main", "--base")):
    """Verify, push the task branch and open a GitHub PR with the provenance body."""
    _guard(lambda: typer.echo(open_pr(_ref(task), base=base)))
