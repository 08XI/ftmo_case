"""Append-only, hash-chained ledger: one canonical JSON object per line."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .errors import LedgerError
from .schemas import LedgerEntry

GENESIS = "0" * 64
LEDGER_FILE = "ledger.jsonl"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def entry_hash(data: dict[str, Any]) -> str:
    return sha256_bytes(canonical({k: v for k, v in data.items() if k != "hash"}))


def load(task_dir: Path) -> list[LedgerEntry]:
    path = Path(task_dir) / LEDGER_FILE
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise LedgerError(f"{path.name}: not valid UTF-8: {exc}") from exc
    entries = []
    for lineno, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        try:
            entries.append(LedgerEntry.model_validate_json(line))
        except ValidationError as exc:
            raise LedgerError(f"{path.name} line {lineno}: invalid entry: {exc}") from exc
    return entries


def append(task_dir: Path, **fields: Any) -> LedgerEntry:
    """Append one entry. seq, prev_hash and hash are computed here, never by callers."""
    entries = load(task_dir)
    data = {**fields, "seq": len(entries), "prev_hash": entries[-1].hash if entries else GENESIS, "hash": ""}
    draft = LedgerEntry.model_validate(data).model_dump(mode="json")
    draft["hash"] = entry_hash(draft)
    entry = LedgerEntry.model_validate(draft)
    path = Path(task_dir) / LEDGER_FILE
    if path.exists() and path.stat().st_size > 0:
        with path.open("rb") as fh:
            fh.seek(-1, 2)
            if fh.read(1) != b"\n":
                raise LedgerError(f"{path.name}: missing trailing newline; refusing to append")
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(canonical(entry.model_dump(mode="json")).decode("utf-8") + "\n")
    return entry


def check_chain(entries: list[LedgerEntry]) -> list[str]:
    errors = []
    prev = GENESIS
    for index, entry in enumerate(entries):
        if entry.seq != index:
            errors.append(f"entry at position {index} has seq {entry.seq}")
        if entry.prev_hash != prev:
            errors.append(f"entry {entry.seq}: prev_hash does not match the previous entry")
        if entry_hash(entry.model_dump(mode="json")) != entry.hash:
            errors.append(f"entry {entry.seq}: content does not match its hash (edited after writing)")
        prev = entry.hash
    return errors
