import pytest

from factory import ledger
from factory.errors import LedgerError
from factory.schemas import Actor


def _append(task_dir, role="initiator", cost=0.0):
    return ledger.append(
        task_dir, task="T-1", role=role, actor=Actor(kind="human", id="alice"),
        on_behalf_of="alice", cost_usd=cost, started_at="t0", ended_at="t1",
    )


def test_append_builds_a_valid_chain(tmp_path):
    first = _append(tmp_path)
    second = _append(tmp_path, role="planner", cost=0.41)
    entries = ledger.load(tmp_path)
    assert [e.seq for e in entries] == [0, 1]
    assert first.prev_hash == ledger.GENESIS
    assert second.prev_hash == first.hash
    assert ledger.check_chain(entries) == []


def test_edited_entry_breaks_the_chain(tmp_path):
    _append(tmp_path)
    _append(tmp_path, role="planner", cost=0.41)
    path = tmp_path / ledger.LEDGER_FILE
    path.write_text(path.read_text(encoding="utf-8").replace("0.41", "0.01"), encoding="utf-8", newline="\n")
    errors = ledger.check_chain(ledger.load(tmp_path))
    assert any("does not match its hash" in e for e in errors)


def test_deleted_entry_breaks_the_chain(tmp_path):
    for _ in range(3):
        _append(tmp_path)
    path = tmp_path / ledger.LEDGER_FILE
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    path.write_text(lines[0] + lines[2], encoding="utf-8", newline="\n")
    errors = ledger.check_chain(ledger.load(tmp_path))
    assert any("prev_hash" in e for e in errors)


def test_invalid_line_raises(tmp_path):
    (tmp_path / ledger.LEDGER_FILE).write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(LedgerError):
        ledger.load(tmp_path)
