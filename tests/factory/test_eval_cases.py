from evals.reviewer_eval import CASES, apply_edits


def test_every_case_applies_cleanly():
    for case in CASES:
        patched = apply_edits(case)
        assert patched, case.name
