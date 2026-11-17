"""Reviewer eval: does the blind reviewer role catch seeded invariant bugs?

Usage: python -m evals.reviewer_eval [--runtime claude] [--model sonnet]
Each case patches a temp copy of the repo and asks the reviewer for a verdict.
Bug cases should get changes_requested; the control case should be approved.
Cases are anchored on frozen copies in evals/baseline/, so later changes to
orders/ do not break the eval.
"""
from __future__ import annotations

import argparse
import difflib
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from factory.errors import FactoryError
from factory.prompts import build_prompt, policy_for, role_prompt_path
from factory.runtime import extract_json_block, get_runtime
from factory.schemas import Review, Task

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "evals" / "baseline"
ORDER = "orders/order.py"
TESTS = "tests/orders/test_order.py"
GOAL = "Allow cancelling the remaining quantity of a partially filled order. Filled quantity is kept."

CONTROL = [
    (ORDER, "        if self.state is not OrderState.NEW:\n            raise OrderError(f\"cannot cancel",
     "        if self.state not in (OrderState.NEW, OrderState.PARTIALLY_FILLED):\n"
     "            raise OrderError(f\"cannot cancel"),
    (TESTS, "", "\n\ndef test_cancel_partially_filled_order_keeps_filled_quantity():\n"
                "    order = Order(\"o-9\", Side.BUY, Decimal(\"10\"))\n    order.fill(Decimal(\"4\"))\n"
                "    order.cancel()\n    assert order.state is OrderState.CANCELLED\n"
                "    assert order.filled == Decimal(\"4\")\n"),
]


@dataclass
class Case:
    name: str
    edits: list[tuple[str, str, str]]  # (path, old, new); old == "" appends
    expect: str


CASES = [
    Case("control-correct-change", CONTROL, "approved"),
    Case("cancel-allowed-from-filled", CONTROL + [
        (ORDER, "(OrderState.NEW, OrderState.PARTIALLY_FILLED):\n            raise OrderError(f\"cannot cancel",
         "(OrderState.NEW, OrderState.PARTIALLY_FILLED, OrderState.FILLED):\n"
         "            raise OrderError(f\"cannot cancel")], "changes_requested"),
    Case("cancel-resets-filled", CONTROL + [
        (ORDER, "        self.state = OrderState.CANCELLED\n",
         "        self.filled = Decimal(\"0\")\n        self.state = OrderState.CANCELLED\n")], "changes_requested"),
    Case("overfill-check-per-fill-only", CONTROL + [
        (ORDER, "if self.filled + qty > self.quantity:", "if qty > self.quantity:")], "changes_requested"),
    Case("mutate-before-validate", CONTROL + [
        (ORDER, "        if self.filled + qty > self.quantity:\n            raise OrderError(\"fill would exceed order "
                "quantity\")\n        self.filled += qty\n",
         "        self.filled += qty\n        if self.filled > self.quantity:\n            raise OrderError(\"fill "
         "would exceed order quantity\")\n")], "changes_requested"),
]


def apply_edits(case: Case) -> dict[str, tuple[str, str]]:
    """Return {path: (original, patched)} for every file the case touches."""
    files: dict[str, tuple[str, str]] = {}
    for path, old, new in case.edits:
        original = (BASELINE / path).read_text(encoding="utf-8")
        current = files.get(path, (original, original))[1]
        if old == "":
            patched = current + new
        elif old in current:
            patched = current.replace(old, new, 1)
        else:
            raise ValueError(f"{case.name}: anchor not found in {path}")
        files[path] = (original, patched)
    return files


def run_case(case: Case, runtime) -> tuple[str, str]:
    files = apply_edits(case)
    diff = "".join("".join(difflib.unified_diff(o.splitlines(True), p.splitlines(True), f"a/{path}", f"b/{path}"))
                   for path, (o, p) in files.items())
    task = Task(id="T-eval", title="Cancel partial fills", goal=GOAL, initiator="eval", base_commit="0" * 40,
                branch="factory/T-eval", created_at="2026-01-01T00:00:00Z")
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for part in ("orders", "tests", ".factory/roles", "AGENTS.md", "CLAUDE.md", "pyproject.toml"):
            src, dst = ROOT / part, work / part
            if src.is_dir():
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", ".hypothesis"))
            elif src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        for path, (_, patched) in files.items():
            (work / path).write_text(patched, encoding="utf-8", newline="\n")
        prompt = build_prompt(role_prompt_path(ROOT, "reviewer").read_text(encoding="utf-8"), [
            ("Task", task.model_dump_json(indent=2)),
            ("Diff under review", f"```diff\n{diff}\n```"),
            ("Test run by the factory", "Not run for this eval. You may run the tests yourself."),
        ], Review)
        try:
            result = runtime.run(role="reviewer", prompt=prompt, policy=policy_for("reviewer", task),
                                 cwd=work, attempt=0)
            review = Review.model_validate(extract_json_block(result.text))
        except (FactoryError, ValueError) as exc:
            return "error", str(exc)[:120]
    return review.verdict, f"${result.cost_usd:.2f} {review.summary[:80]}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", default="claude")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    runtime = get_runtime(args.runtime, args.model)
    rows, correct = [], 0
    for case in CASES:
        got, detail = run_case(case, runtime)
        ok = got == case.expect
        correct += ok
        rows.append(f"| {case.name} | {case.expect} | {got} | {'yes' if ok else 'NO'} | {detail} |")
        print(rows[-1], flush=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    report = "\n".join([f"# Reviewer eval ({stamp}, model: {args.model or 'default'})", "",
                        "| case | expected | got | correct | detail |", "|---|---|---|---|---|", *rows, "",
                        f"Score: {correct}/{len(CASES)}", ""])
    out = ROOT / "evals" / "results" / "latest.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8", newline="\n")
    print(f"\nScore: {correct}/{len(CASES)} -> {out}")


if __name__ == "__main__":
    main()
