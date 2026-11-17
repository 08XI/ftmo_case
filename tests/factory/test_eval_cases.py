from evals import reviewer_eval
from evals.reviewer_eval import CASES, apply_edits


def test_every_case_applies_cleanly():
    for case in CASES:
        patched = apply_edits(case)
        assert patched, case.name


def test_cases_do_not_depend_on_live_module(monkeypatch, tmp_path):
    # With ROOT pointing at an empty dir, cases must still apply: originals
    # come from the frozen baseline, not the live orders/ module.
    real_baseline = reviewer_eval.BASELINE
    monkeypatch.setattr(reviewer_eval, "ROOT", tmp_path)
    monkeypatch.setattr(reviewer_eval, "BASELINE", real_baseline)
    for case in CASES:
        assert apply_edits(case), case.name
