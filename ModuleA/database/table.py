from contextlib import nullcontext

from .bplustree import BPlusTree


class Table:
    def __init__(
        self,
        name,
        schema,
        order,
        search_key,
        constraints=None,
        db_name=None,
        tx_manager=None,
        db_manager=None,
    ):
        self.name = name
        self.schema = schema
        self.search_key = search_key
        self.data = BPlusTree(order=order)
        self.db_name = db_name
        self.tx_manager = tx_manager
        self.db_manager = db_manager
        self.constraints = constraints or {}

    def _begin_if_needed(self, tx_id):
        if self.tx_manager is None:
            return tx_id, False
        if tx_id is None:
            tx_id = self.tx_manager.begin()
            return tx_id, True
        self.tx_manager.ensure_active(tx_id)
        return tx_id, False

    def _finish_auto_tx(self, tx_id, auto_tx, ok):
        if not auto_tx or self.tx_manager is None:
            return
        if ok:
            self.tx_manager.commit(tx_id)
        else:
            self.tx_manager.rollback(tx_id)

    def _isolation_guard(self):
        if self.db_manager is None:
            return nullcontext()
        return self.db_manager.isolation_lock

    def validate_record(self, record):
        if not isinstance(record, dict):
            raise ValueError("Record must be a dictionary")
        if self.search_key not in record:
            raise ValueError(f"Record must contain search key: {self.search_key}")
        for field, schema_type in self.schema.items():
            if field in record:
                # We can add specialized schema checking here if needed
                pass
        return self._validate_constraints(record)

    def _validate_constraints(self, record):
        primary_key = self.constraints.get("primary_key", True)
        non_negative = self.constraints.get("non_negative", [])
        for field in non_negative:
            if field not in record:
                continue
            value = record.get(field)
            if value is None:
                continue
            if not isinstance(value, (int, float)):
                raise ValueError(f"Field {field} must be numeric for non_negative")
            if value < 0:
                raise ValueError(f"Field {field} must be non-negative")

        references = {}
        references.update(self.constraints.get("references", {}))
        references.update(self.constraints.get("foreign_keys", {}))
        if references and self.db_manager is None:
            raise ValueError("Reference constraints require a database manager")
        for field, ref in references.items():
            if field not in record:
                continue
            if isinstance(ref, dict):
                ref_table_name = ref.get("table")
                ref_key = ref.get("key")
            else:
                ref_table_name, ref_key = ref
            if not ref_table_name or not ref_key:
                raise ValueError(f"Invalid reference constraint for {field}")
            ref_table = self.db_manager.get_table(self.db_name, ref_table_name)
            if ref_table is None:
                raise ValueError(f"Referenced table {ref_table_name} not found")
            if ref_table.get(record.get(field)) is None:
                raise ValueError(
                    f"Invalid reference for {field}: {record.get(field)}"
                )
        return primary_key

    def insert(self, record, tx_id=None):
        key = record[self.search_key]
        tx_id, auto_tx = self._begin_if_needed(tx_id)
        try:
            primary_key = self.validate_record(record)
            old_value = self.data.search(key)
            if primary_key and old_value is not None:
                raise ValueError(f"Primary key already exists: {key}")
            if self.tx_manager is not None and tx_id is not None:
                self.tx_manager.log_op(
                    tx_id,
                    "TX_INSERT",
                    self.db_name,
                    self.name,
                    key,
                    old_value,
                    record,
                )
            self.data.insert(key, record)
            self._finish_auto_tx(tx_id, auto_tx, True)
            return old_value
        except Exception:
            self._finish_auto_tx(tx_id, auto_tx, False)
            raise

    def get(self, record_id):
        with self._isolation_guard():
            return self.data.search(record_id)

    def get_all(self):
        with self._isolation_guard():
            return [v for k, v in self.data.get_all()]

    def search(self, constraints):
        with self._isolation_guard():
            results = []
            for key, record in self.data.get_all():
                match = True
                for k, v in constraints.items():
                    if record.get(k) != v:
                        match = False
                        break
                if match:
                    results.append(record)
            return results

    def delete(self, record_id, tx_id=None):
        tx_id, auto_tx = self._begin_if_needed(tx_id)
        try:
            old_value = self.data.search(record_id)
            if old_value is None:
                self._finish_auto_tx(tx_id, auto_tx, True)
                return None
            if self.tx_manager is not None and tx_id is not None:
                self.tx_manager.log_op(
                    tx_id,
                    "TX_DELETE",
                    self.db_name,
                    self.name,
                    record_id,
                    old_value,
                    None,
                )
            self.data.delete(record_id)
            self._finish_auto_tx(tx_id, auto_tx, True)
            return old_value
        except Exception:
            self._finish_auto_tx(tx_id, auto_tx, False)
            raise

    def update(self, record_id, new_record, tx_id=None):
        tx_id, auto_tx = self._begin_if_needed(tx_id)
        try:
            primary_key = self.validate_record(new_record)
            old_value = self.data.search(record_id)
            if old_value is None:
                self._finish_auto_tx(tx_id, auto_tx, True)
                return None
            if primary_key and new_record.get(self.search_key) != record_id:
                raise ValueError("Primary key cannot be changed")
            if self.tx_manager is not None and tx_id is not None:
                self.tx_manager.log_op(
                    tx_id,
                    "TX_UPDATE",
                    self.db_name,
                    self.name,
                    record_id,
                    old_value,
                    new_record,
                )
            self.data.update(record_id, new_record)
            self._finish_auto_tx(tx_id, auto_tx, True)
            return old_value
        except Exception:
            self._finish_auto_tx(tx_id, auto_tx, False)
            raise

    def range_query(self, field, start_value, end_value):
        with self._isolation_guard():
            if field == self.search_key:
                results = self.data.range_query(start_value, end_value)
                return [v for k, v in results]
            results = []
            for k, record in self.data.get_all():
                val = record.get(field)
                if val is not None and start_value <= val <= end_value:
                    results.append(record)
            return results

    def apply_log_op(self, op, undo=False):
        key = op.get("key")
        if undo:
            self._apply_set(key, op.get("old"))
            return
        if op.get("type") == "TX_DELETE":
            self._apply_delete(key)
        else:
            self._apply_set(key, op.get("new"))

    def _apply_set(self, key, record):
        if record is None:
            self.data.delete(key)
        else:
            self.data.insert(key, record)

    def _apply_delete(self, key):
        self.data.delete(key)
