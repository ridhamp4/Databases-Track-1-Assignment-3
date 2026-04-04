import json
import os
import threading
from dataclasses import dataclass, field


@dataclass
class TxState:
    tx_id: int
    ops: list = field(default_factory=list)
    holds_lock: bool = False


class TransactionManager:
    def __init__(self, log_path, db_manager=None, isolation_lock=None):
        self.log_path = log_path
        self._db_manager = db_manager
        self._tx_lock = threading.Lock()
        self._log_lock = threading.Lock()
        self._global_lock = isolation_lock or threading.RLock()
        self._next_tx_id = 0
        self._active = {}
        self._ensure_log_dir()

    def _ensure_log_dir(self):
        log_dir = os.path.dirname(self.log_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

    def begin(self):
        with self._tx_lock:
            self._next_tx_id += 1
            tx_id = self._next_tx_id
            self._active[tx_id] = TxState(tx_id)
        self._global_lock.acquire()
        self._active[tx_id].holds_lock = True
        try:
            self._append_log({"type": "TX_START", "tx_id": tx_id})
        except Exception:
            self._global_lock.release()
            with self._tx_lock:
                self._active.pop(tx_id, None)
            raise
        return tx_id

    def ensure_active(self, tx_id):
        tx = self._active.get(tx_id)
        if tx is None:
            raise ValueError(f"Transaction {tx_id} is not active")
        return tx

    def log_op(self, tx_id, op_type, db_name, table_name, key, old_value, new_value):
        tx = self.ensure_active(tx_id)
        entry = {
            "type": op_type,
            "tx_id": tx_id,
            "db": db_name,
            "table": table_name,
            "key": key,
            "old": old_value,
            "new": new_value,
        }
        self._append_log(entry)
        tx.ops.append(entry)

    def commit(self, tx_id):
        tx = self.ensure_active(tx_id)
        try:
            self._append_log({"type": "TX_COMMIT", "tx_id": tx_id})
        except Exception:
            if self._db_manager is not None:
                for op in reversed(tx.ops):
                    self._db_manager.apply_log_op(op, undo=True)
            self._release_tx(tx_id)
            raise
        self._release_tx(tx_id)

    def rollback(self, tx_id):
        tx = self.ensure_active(tx_id)
        if self._db_manager is not None:
            for op in reversed(tx.ops):
                self._db_manager.apply_log_op(op, undo=True)
        self._append_log({"type": "TX_ROLLBACK", "tx_id": tx_id})
        self._release_tx(tx_id)

    def recover(self, db_manager):
        if not os.path.exists(self.log_path):
            return

        started = set()
        committed = set()
        ops = []

        with open(self.log_path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                entry_type, payload = self._parse_log_line(line)
                tx_id = payload.get("tx_id")

                if entry_type == "TX_START":
                    if tx_id is not None:
                        started.add(tx_id)
                elif entry_type == "TX_COMMIT":
                    if tx_id is not None:
                        committed.add(tx_id)
                elif entry_type == "TX_ROLLBACK":
                    if tx_id is not None:
                        started.add(tx_id)
                elif entry_type in ("TX_INSERT", "TX_UPDATE", "TX_DELETE"):
                    ops.append(payload)

        if hasattr(db_manager, "apply_recovery_from_log"):
            db_manager.apply_recovery_from_log(ops, started, committed)
        else:
            redo_ops = [op for op in ops if op.get("tx_id") in committed]
            undo_ops = [
                op
                for op in reversed(ops)
                if op.get("tx_id") in started and op.get("tx_id") not in committed
            ]
            db_manager.apply_recovery_ops(redo_ops, undo_ops)

    def _append_log(self, entry):
        line = self._format_entry(entry)
        with self._log_lock:
            with open(self.log_path, "a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())

    def _format_entry(self, entry):
        entry_type = entry.get("type", "UNKNOWN")
        payload = json.dumps(
            entry,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        )
        return f"{entry_type}|{payload}\n"

    def _parse_log_line(self, line):
        if "|" not in line:
            return line, {"type": line}
        entry_type, payload = line.split("|", 1)
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = {"type": entry_type}
        if "type" not in data:
            data["type"] = entry_type
        return entry_type, data

    def _release_tx(self, tx_id):
        with self._tx_lock:
            tx = self._active.pop(tx_id, None)
        if tx is not None and tx.holds_lock:
            self._global_lock.release()
