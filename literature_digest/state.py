from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def state_scope(config):
    """Scope every ledger operation by profile AND actual delivery audience."""
    return json.dumps({"profile": config.get("profile_id", "default"), "recipient": config["recipient"].lower()}, sort_keys=True)


class State:
    def __init__(self, path, scope=""):
        self.path, self.scope = Path(path), scope
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.path.chmod(0o600)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS deliveries_v2 (scope TEXT NOT NULL, id TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(scope,id));
            CREATE TABLE IF NOT EXISTS sent_papers_v2 (scope TEXT NOT NULL, alias TEXT NOT NULL, digest_id TEXT NOT NULL, sent_at TEXT NOT NULL, PRIMARY KEY(scope,alias));
            CREATE TABLE IF NOT EXISTS metadata_v2 (scope TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(scope,key));
        """)
        self._migrate_v1()
        self.db.commit()

    def _migrate_v1(self):
        """Copy legacy default-profile outboxes without deleting the original ledger."""
        if self.db.execute("PRAGMA user_version").fetchone()[0] >= 2:
            return
        names = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "deliveries" in names:
            for identifier, status, raw, created, updated in self.db.execute("SELECT id,status,payload,created_at,updated_at FROM deliveries").fetchall():
                payload = json.loads(raw)
                scope = state_scope({"recipient": payload["recipient"]}) if payload.get("recipient") else ""
                self.db.execute("INSERT OR IGNORE INTO deliveries_v2 VALUES(?,?,?,?,?,?)", (scope, identifier, status, raw, created, updated))
                if status == "sent":
                    for alias in payload.get("aliases", []):
                        self.db.execute("INSERT OR IGNORE INTO sent_papers_v2 VALUES(?,?,?,?)", (scope, alias, identifier, updated))
                    if payload.get("harvest_until"):
                        self.db.execute("INSERT INTO metadata_v2 VALUES(?,?,?) ON CONFLICT(scope,key) DO UPDATE SET value=MAX(value,excluded.value)", (scope, "checkpoint", payload["harvest_until"]))
        self.db.execute("PRAGMA user_version=2")

    def close(self):
        self.db.close()

    @contextmanager
    def lock(self):
        try:
            import fcntl
        except ImportError:
            raise RuntimeError("Concurrency protection requires Linux/macOS or Windows WSL") from None
        with open(str(self.path) + ".lock", "a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("Another digest process is using this state database") from None
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def checkpoint(self):
        row = self.db.execute("SELECT value FROM metadata_v2 WHERE scope=? AND key='checkpoint'", (self.scope,)).fetchone()
        return row[0] if row else None

    def was_sent(self, paper):
        return any(self.db.execute("SELECT 1 FROM sent_papers_v2 WHERE scope=? AND alias=?", (self.scope, a)).fetchone() for a in paper.aliases)

    def get(self, digest_id):
        row = self.db.execute("SELECT status,payload FROM deliveries_v2 WHERE scope=? AND id=?", (self.scope, digest_id)).fetchone()
        return {"id": digest_id, "status": row[0], "payload": json.loads(row[1])} if row else None

    def sent_on(self, local_day):
        for identifier, raw in self.db.execute("SELECT id,payload FROM deliveries_v2 WHERE scope=? AND status='sent' ORDER BY updated_at DESC", (self.scope,)):
            if json.loads(raw).get("harvest_until") == local_day:
                return identifier
        return None

    def recent(self):
        return [{"digest_id": r[0], "status": r[1], "updated_at": r[2]} for r in self.db.execute("SELECT id,status,updated_at FROM deliveries_v2 WHERE scope=? ORDER BY created_at DESC LIMIT 30", (self.scope,))]

    def unresolved(self):
        return [{"id": r[0], "status": r[1]} for r in self.db.execute("SELECT id,status FROM deliveries_v2 WHERE scope=? AND status IN ('sending','uncertain')", (self.scope,))]

    def prepare(self, digest_id, payload):
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute("INSERT OR IGNORE INTO deliveries_v2 VALUES(?,?,?,?,?,?)", (self.scope, digest_id, "prepared", json.dumps(payload, ensure_ascii=False), now, now))
        self.db.commit()
        return self.get(digest_id)

    def status(self, digest_id, status):
        self.db.execute("UPDATE deliveries_v2 SET status=?,updated_at=? WHERE scope=? AND id=?", (status, datetime.now(timezone.utc).isoformat(), self.scope, digest_id))
        self.db.commit()

    def mark_sent(self, digest_id):
        item = self.get(digest_id)
        if not item:
            raise ValueError("Digest was not found in this reader's outbox")
        now = datetime.now(timezone.utc).isoformat()
        with self.db:
            for alias in item["payload"]["aliases"]:
                self.db.execute("INSERT OR IGNORE INTO sent_papers_v2 VALUES(?,?,?,?)", (self.scope, alias, digest_id, now))
            self.db.execute("UPDATE deliveries_v2 SET status='sent',updated_at=? WHERE scope=? AND id=?", (now, self.scope, digest_id))
            self.db.execute("INSERT INTO metadata_v2 VALUES(?,?,?) ON CONFLICT(scope,key) DO UPDATE SET value=MAX(value,excluded.value)", (self.scope, "checkpoint", item["payload"]["harvest_until"]))

    def payload_has_sent_aliases(self, payload):
        return any(self.db.execute("SELECT 1 FROM sent_papers_v2 WHERE scope=? AND alias=?", (self.scope, a)).fetchone() for a in payload["aliases"])

    def resolve(self, digest_id, decision):
        item = self.get(digest_id)
        if not item or item["status"] not in ("sending", "uncertain"):
            raise ValueError("Only uncertain or interrupted deliveries can be resolved")
        if decision == "sent":
            self.mark_sent(digest_id)
        elif decision == "retry":
            self.status(digest_id, "prepared")
        else:
            raise ValueError("Invalid resolution")
