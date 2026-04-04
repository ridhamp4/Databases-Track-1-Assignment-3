import os
import threading

from .transaction import TransactionManager


class DatabaseManager:
    def __init__(self, log_path=None):
        self.databases = {}
        self._pending_recovery = {}
        self._isolation_lock = threading.RLock()
        if log_path is None:
            log_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "db_transactions.log")
            )
        self.tx_manager = TransactionManager(
            log_path=log_path,
            db_manager=self,
            isolation_lock=self._isolation_lock,
        )
        self.tx_manager.recover(self)

    def create_database(self, db_name):
        if db_name not in self.databases:
            self.databases[db_name] = {}
            return True
        return False

    def delete_database(self, db_name):
        if db_name in self.databases:
            del self.databases[db_name]
            return True
        return False

    def list_databases(self):
        return list(self.databases.keys())

    def create_table(self, db_name, table_name, schema, order, search_key, constraints=None):
        if db_name not in self.databases:
            return False
        if table_name not in self.databases[db_name]:
            from .table import Table
            self.databases[db_name][table_name] = Table(
                table_name,
                schema,
                order,
                search_key,
                constraints=constraints,
                db_name=db_name,
                tx_manager=self.tx_manager,
                db_manager=self,
            )
            self._apply_pending_recovery(db_name, table_name)
            return True
        return False

    def delete_table(self, db_name, table_name):
        if db_name in self.databases and table_name in self.databases[db_name]:
            del self.databases[db_name][table_name]
            self._pending_recovery.pop((db_name, table_name), None)
            return True
        return False

    def list_tables(self, db_name):
        if db_name in self.databases:
            return list(self.databases[db_name].keys())
        return []

    def get_table(self, db_name, table_name):
        if db_name in self.databases:
            return self.databases[db_name].get(table_name)
        return None

    @property
    def isolation_lock(self):
        return self._isolation_lock

    def begin(self):
        return self.tx_manager.begin()

    def commit(self, tx_id):
        self.tx_manager.commit(tx_id)

    def rollback(self, tx_id):
        self.tx_manager.rollback(tx_id)

    def apply_recovery_ops(self, redo_ops, undo_ops):
        for op in redo_ops:
            self.apply_log_op(op, undo=False)
        for op in undo_ops:
            self.apply_log_op(op, undo=True)

    def apply_recovery_from_log(self, ops, started, committed, rolled_back=None):
        if rolled_back is None:
            rolled_back = set()
        incomplete = started - committed - rolled_back
        redo_ops = [op for op in ops if op.get("tx_id") in committed]
        undo_ops = [
            op
            for op in reversed(ops)
            if op.get("tx_id") in incomplete
        ]
        self.apply_recovery_ops(redo_ops, undo_ops)

    def apply_log_op(self, op, undo=False):
        db_name = op.get("db")
        table_name = op.get("table")
        if not db_name or not table_name:
            return
        table = self.get_table(db_name, table_name)
        if table is None:
            pending = self._pending_recovery.setdefault(
                (db_name, table_name), {"redo": [], "undo": []}
            )
            if undo:
                pending["undo"].append(op)
            else:
                pending["redo"].append(op)
            return
        table.apply_log_op(op, undo=undo)

    def _apply_pending_recovery(self, db_name, table_name):
        pending = self._pending_recovery.pop((db_name, table_name), None)
        if not pending:
            return
        table = self.get_table(db_name, table_name)
        if table is None:
            return
        for op in pending["redo"]:
            table.apply_log_op(op, undo=False)
        for op in pending["undo"]:
            table.apply_log_op(op, undo=True)
