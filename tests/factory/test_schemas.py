from pathlib import Path

import pytest
from pydantic import ValidationError

from factory.schemas import Handoff, Review, export

ROOT = Path(__file__).resolve().parents[2]


def test_handoff_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        Handoff.model_validate({
            "summary": "s", "done": [], "remaining": [], "files_touched": [],
            "tests": "passing", "status": "complete", "mood": "great",
        })


def test_approved_review_cannot_have_blockers():
    with pytest.raises(ValidationError):
        Review.model_validate({
            "verdict": "approved", "summary": "ok",
            "findings": [{"severity": "blocker", "file": "a.py", "message": "broken"}],
        })


def test_spec_files_match_models(tmp_path):
    for generated in export(tmp_path):
        committed = ROOT / "spec" / generated.name
        assert committed.exists(), "run: python -m factory.schemas"
        assert committed.read_text(encoding="utf-8") == generated.read_text(encoding="utf-8"), (
            "spec is stale; run: python -m factory.schemas"
        )
