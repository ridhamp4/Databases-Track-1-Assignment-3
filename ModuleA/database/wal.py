"""
Write-Ahead Log (WAL) for crash recovery.

Every mutation (INSERT, UPDATE, DELETE) is logged to disk BEFORE being applied.
On crash recovery, the WAL is replayed: committed transactions are re-applied,
uncommitted ones are discarded.

Log format (one JSON object per line):
  {"lsn": 1, "txn_id": "t1", "op": "INSERT", "db": "d", "table": "t", "key": 1, "value": {...}, "old_value": null, "ts": "..."}
  {"lsn": 2, "txn_id": "t1", "op": "COMMIT", "ts": "..."}
"""

import json
import os
import time
import threading
from datetime import datetime


class WAL:
    def __init__(self, log_dir="wal_logs"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, "wal.log")
        self.checkpoint_file = os.path.join(log_dir, "checkpoint.json")
        self.lock = threading.Lock()
        self.lsn = 0  # Log Sequence Number
        self._load_lsn()

    def _load_lsn(self):
        """Resume LSN from existing log file."""
        if os.path.exists(self.log_file):
            with open(self.log_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entry = json.loads(line)
                            self.lsn = max(self.lsn, entry.get("lsn", 0))
                        except json.JSONDecodeError:
                            pass

    def _next_lsn(self):
        self.lsn += 1
        return self.lsn

    def log(self, txn_id, op, db_name=None, table_name=None,
            key=None, value=None, old_value=None):
        """Append a log entry and flush to disk."""
        with self.lock:
            entry = {
                "lsn": self._next_lsn(),
                "txn_id": txn_id,
                "op": op,
                "ts": datetime.utcnow().isoformat(),
            }
            if db_name is not None:
                entry["db"] = db_name
            if table_name is not None:
                entry["table"] = table_name
            if key is not None:
                entry["key"] = key
            if value is not None:
                entry["value"] = value
            if old_value is not None:
                entry["old_value"] = old_value

            with open(self.log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
                f.flush()
                os.fsync(f.fileno())

            return entry["lsn"]

    def log_begin(self, txn_id):
        return self.log(txn_id, "BEGIN")

    def log_commit(self, txn_id):
        return self.log(txn_id, "COMMIT")

    def log_rollback(self, txn_id):
        return self.log(txn_id, "ROLLBACK")

    def log_insert(self, txn_id, db_name, table_name, key, value):
        return self.log(txn_id, "INSERT", db_name, table_name, key, value)

    def log_update(self, txn_id, db_name, table_name, key, new_value, old_value):
        return self.log(txn_id, "UPDATE", db_name, table_name, key, new_value, old_value)

    def log_delete(self, txn_id, db_name, table_name, key, old_value):
        return self.log(txn_id, "DELETE", db_name, table_name, key, old_value=old_value)

    def read_log(self):
        """Read all log entries."""
        entries = []
        if not os.path.exists(self.log_file):
            return entries
        with open(self.log_file, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries

    def get_committed_txns(self):
        """Return set of transaction IDs that have a COMMIT record."""
        entries = self.read_log()
        committed = set()
        rolled_back = set()
        for e in entries:
            if e["op"] == "COMMIT":
                committed.add(e["txn_id"])
            elif e["op"] == "ROLLBACK":
                rolled_back.add(e["txn_id"])
        return committed, rolled_back

    def get_recovery_actions(self):
        """
        Determine which operations to redo (committed) and undo (uncommitted).
        Returns (redo_ops, undo_ops).
        redo_ops: list of data operations from committed txns (in order)
        undo_ops: list of data operations from uncommitted txns (in reverse order)
        """
        entries = self.read_log()
        committed, rolled_back = self.get_committed_txns()
        data_ops = [e for e in entries if e["op"] in ("INSERT", "UPDATE", "DELETE")]

        redo_ops = [e for e in data_ops if e["txn_id"] in committed]
        undo_ops = [e for e in data_ops
                    if e["txn_id"] not in committed and e["txn_id"] not in rolled_back]
        undo_ops.reverse()  # undo in reverse order

        return redo_ops, undo_ops

    def checkpoint(self, snapshot_data):
        """Write a checkpoint with current database snapshot."""
        with self.lock:
            ckpt = {
                "lsn": self.lsn,
                "ts": datetime.utcnow().isoformat(),
                "snapshot": snapshot_data,
            }
            with open(self.checkpoint_file, "w") as f:
                json.dump(ckpt, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # Truncate the WAL after checkpoint
            with open(self.log_file, "w") as f:
                f.truncate()

    def load_checkpoint(self):
        """Load the last checkpoint if it exists."""
        if os.path.exists(self.checkpoint_file):
            with open(self.checkpoint_file, "r") as f:
                return json.load(f)
        return None

    def clear(self):
        """Clear the WAL (for testing)."""
        with self.lock:
            if os.path.exists(self.log_file):
                with open(self.log_file, "w") as f:
                    f.truncate()
            self.lsn = 0
