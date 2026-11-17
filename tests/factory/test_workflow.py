from factory.schemas import AGENT_ROLES, Actor, LedgerEntry
from factory.workflow import allowed_next, describe_state, is_pr_ready, sequence_errors


def chain(*roles):
    return [
        LedgerEntry(seq=i, task="T-1", role=role,
                    actor=Actor(kind="agent" if role in AGENT_ROLES else "human", id="x"),
                    on_behalf_of="alice", started_at="t", ended_at="t", prev_hash="p", hash="h")
        for i, role in enumerate(roles)
    ]


def verdicts(mapping):
    return lambda entry: mapping.get(entry.seq)


HAPPY = ("initiator", "planner", "plan_approval", "implementer", "reviewer")


def test_happy_sequence_is_valid_and_pr_ready():
    entries = chain(*HAPPY)
    v = verdicts({4: "approved"})
    assert sequence_errors(entries, v, 3) == []
    assert is_pr_ready(entries, v)
    assert describe_state(entries, v, 3).startswith("approved")


def test_reviewer_cannot_run_before_implementation():
    entries = chain("initiator", "planner", "plan_approval")
    assert "reviewer" not in allowed_next(entries, verdicts({}), 3)


def test_skipping_plan_approval_is_flagged():
    entries = chain("initiator", "planner", "implementer", "reviewer")
    errors = sequence_errors(entries, verdicts({3: "approved"}), 3)
    assert any("entry 2" in e for e in errors)


def test_review_loop_limit_hands_over_to_a_human():
    entries = chain("initiator", "planner", "plan_approval", "implementer", "reviewer", "implementer", "reviewer")
    v = verdicts({4: "changes_requested", 6: "changes_requested"})
    assert allowed_next(entries, v, 2) == {"human_change"}
    assert allowed_next(entries, v, 3) == {"implementer", "human_change"}
    assert not is_pr_ready(entries, v)
