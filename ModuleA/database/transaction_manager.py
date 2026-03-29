"""
Transaction Manager for the B+ Tree Database.

Provides BEGIN, COMMIT, ROLLBACK semantics with WAL-based crash recovery.
Each transaction buffers its operations and only applies them on COMMIT.
On ROLLBACK, buffered operations are discarded.
On crash recovery, the WAL is replayed to restore committed state.
"""

import uuid
import threading
import copy
from datetime import datetime
from .wal import WAL


class Transaction:
    """Represents an active transaction."""

    def __init__(self, txn_id):
        self.txn_id = txn_id
        self.operations = []  # list of (op, db, table, key, value, old_value)
        self.started_at = datetime.utcnow().isoformat()
        self.status = "ACTIVE"  # ACTIVE, COMMITTED, ABORTED


class TransactionManager:
    """
    Manages transactions with WAL logging, providing:
    - BEGIN / COMMIT / ROLLBACK
    - Crash recovery via WAL replay
    - Lock-based concurrency control (table-level locks)
    """

    def __init__(self, db_manager, wal_dir="wal_logs"):
        self.db_manager = db_manager
        self.wal = WAL(wal_dir)
        self.active_txns = {}  # txn_id -> Transaction
        self.lock = threading.Lock()
        self.table_locks = {}  # (db, table) -> threading.Lock

    def _get_table_lock(self, db_name, table_name):
        key = (db_name, table_name)
        if key not in self.table_locks:
            self.table_locks[key] = threading.Lock()
        return self.table_locks[key]

    def begin(self):
        """Start a new transaction. Returns the transaction ID."""
        txn_id = f"txn_{uuid.uuid4().hex[:12]}"
        with self.lock:
            txn = Transaction(txn_id)
            self.active_txns[txn_id] = txn
        self.wal.log_begin(txn_id)
        return txn_id

    def _get_txn(self, txn_id):
        txn = self.active_txns.get(txn_id)
        if not txn:
            raise ValueError(f"Transaction {txn_id} not found or already ended")
        if txn.status != "ACTIVE":
            raise ValueError(f"Transaction {txn_id} is {txn.status}")
        return txn

    def insert(self, txn_id, db_name, table_name, record):
        """Buffer an INSERT operation within a transaction."""
        txn = self._get_txn(txn_id)
        table = self.db_manager.get_table(db_name, table_name)
        if not table:
            raise ValueError(f"Table {db_name}.{table_name} not found")

        table.validate_record(record)
        key = record[table.search_key]

        # Check for duplicate
        existing = table.get(key)
        if existing:
            raise ValueError(f"Record with key {key} already exists")

        # Log to WAL before applying
        self.wal.log_insert(txn_id, db_name, table_name, key, record)

        # Apply immediately but track for rollback
        tl = self._get_table_lock(db_name, table_name)
        with tl:
            table.insert(record)
        txn.operations.append(("INSERT", db_name, table_name, key, record, None))

    def update(self, txn_id, db_name, table_name, key, new_record):
        """Buffer an UPDATE operation within a transaction."""
        txn = self._get_txn(txn_id)
        table = self.db_manager.get_table(db_name, table_name)
        if not table:
            raise ValueError(f"Table {db_name}.{table_name} not found")

        table.validate_record(new_record)

        tl = self._get_table_lock(db_name, table_name)
        with tl:
            old_value = table.get(key)
            if old_value is None:
                raise ValueError(f"Record with key {key} not found")
            old_copy = copy.deepcopy(old_value)

            # Log to WAL
            self.wal.log_update(txn_id, db_name, table_name, key, new_record, old_copy)

            # Apply
            table.update(key, new_record)
        txn.operations.append(("UPDATE", db_name, table_name, key, new_record, old_copy))

    def delete(self, txn_id, db_name, table_name, key):
        """Buffer a DELETE operation within a transaction."""
        txn = self._get_txn(txn_id)
        table = self.db_manager.get_table(db_name, table_name)
        if not table:
            raise ValueError(f"Table {db_name}.{table_name} not found")

        tl = self._get_table_lock(db_name, table_name)
        with tl:
            old_value = table.get(key)
            if old_value is None:
                raise ValueError(f"Record with key {key} not found")
            old_copy = copy.deepcopy(old_value)

            # Log to WAL
            self.wal.log_delete(txn_id, db_name, table_name, key, old_copy)

            # Apply
            table.delete(key)
        txn.operations.append(("DELETE", db_name, table_name, key, None, old_copy))

    def commit(self, txn_id):
        """Commit a transaction - write COMMIT to WAL."""
        txn = self._get_txn(txn_id)
        self.wal.log_commit(txn_id)
        txn.status = "COMMITTED"
        with self.lock:
            del self.active_txns[txn_id]
        return True

    def rollback(self, txn_id):
        """Rollback a transaction - undo all operations in reverse order."""
        txn = self._get_txn(txn_id)

        # Undo operations in reverse order
        for op, db_name, table_name, key, value, old_value in reversed(txn.operations):
            table = self.db_manager.get_table(db_name, table_name)
            if not table:
                continue

            tl = self._get_table_lock(db_name, table_name)
            with tl:
                if op == "INSERT":
                    table.delete(key)
                elif op == "UPDATE":
                    table.update(key, old_value)
                elif op == "DELETE":
                    table.insert(old_value)

        self.wal.log_rollback(txn_id)
        txn.status = "ABORTED"
        with self.lock:
            del self.active_txns[txn_id]
        return True

    def recover(self):
        """
        Crash recovery: replay WAL to restore consistent state.
        1. Load checkpoint (if exists) to restore base state.
        2. Redo committed transactions.
        3. Undo uncommitted transactions.
        Returns a recovery report.
        """
        report = {
            "checkpoint_loaded": False,
            "redo_count": 0,
            "undo_count": 0,
            "committed_txns": [],
            "rolled_back_txns": [],
        }

        # Load checkpoint
        ckpt = self.wal.load_checkpoint()
        if ckpt:
            self._restore_from_snapshot(ckpt["snapshot"])
            report["checkpoint_loaded"] = True

        # Get redo/undo operations
        redo_ops, undo_ops = self.wal.get_recovery_actions()

        # Redo committed operations
        for entry in redo_ops:
            self._apply_op(entry)
            report["redo_count"] += 1

        committed, _ = self.wal.get_committed_txns()
        report["committed_txns"] = list(committed)

        # Undo uncommitted operations
        undone_txns = set()
        for entry in undo_ops:
            self._undo_op(entry)
            report["undo_count"] += 1
            undone_txns.add(entry["txn_id"])
        report["rolled_back_txns"] = list(undone_txns)

        return report

    def _apply_op(self, entry):
        """Apply a single WAL entry (redo)."""
        op = entry["op"]
        db_name = entry.get("db")
        table_name = entry.get("table")
        key = entry.get("key")
        value = entry.get("value")

        table = self.db_manager.get_table(db_name, table_name)
        if not table:
            return

        if op == "INSERT":
            existing = table.get(key)
            if not existing:
                table.insert(value)
        elif op == "UPDATE":
            if table.get(key):
                table.update(key, value)
        elif op == "DELETE":
            if table.get(key):
                table.delete(key)

    def _undo_op(self, entry):
        """Undo a single WAL entry."""
        op = entry["op"]
        db_name = entry.get("db")
        table_name = entry.get("table")
        key = entry.get("key")
        old_value = entry.get("old_value")

        table = self.db_manager.get_table(db_name, table_name)
        if not table:
            return

        if op == "INSERT":
            table.delete(key)
        elif op == "UPDATE":
            if old_value and table.get(key):
                table.update(key, old_value)
        elif op == "DELETE":
            if old_value:
                existing = table.get(key)
                if not existing:
                    table.insert(old_value)

    def _restore_from_snapshot(self, snapshot):
        """Restore database state from a checkpoint snapshot."""
        for db_name, tables_data in snapshot.items():
            if db_name not in self.db_manager.databases:
                self.db_manager.create_database(db_name)
            for table_name, table_info in tables_data.items():
                table = self.db_manager.get_table(db_name, table_name)
                if not table:
                    self.db_manager.create_table(
                        db_name, table_name,
                        table_info.get("schema", {}),
                        table_info.get("order", 8),
                        table_info.get("search_key", "id"),
                    )
                    table = self.db_manager.get_table(db_name, table_name)
                for record in table_info.get("records", []):
                    key = record.get(table.search_key)
                    if not table.get(key):
                        table.insert(record)

    def create_snapshot(self):
        """Create a snapshot of current database state for checkpointing."""
        snapshot = {}
        for db_name in self.db_manager.list_databases():
            snapshot[db_name] = {}
            for table_name in self.db_manager.list_tables(db_name):
                table = self.db_manager.get_table(db_name, table_name)
                snapshot[db_name][table_name] = {
                    "schema": table.schema,
                    "order": table.data.order,
                    "search_key": table.search_key,
                    "records": table.get_all(),
                }
        return snapshot

    def checkpoint(self):
        """Create a checkpoint: snapshot + truncate WAL."""
        snapshot = self.create_snapshot()
        self.wal.checkpoint(snapshot)
        return snapshot

    def get_wal_entries(self):
        """Return all WAL entries (for inspection/debugging)."""
        return self.wal.read_log()

    def get_active_transactions(self):
        """Return info about active transactions."""
        return {
            txn_id: {
                "txn_id": txn.txn_id,
                "status": txn.status,
                "started_at": txn.started_at,
                "num_operations": len(txn.operations),
            }
            for txn_id, txn in self.active_txns.items()
        }
