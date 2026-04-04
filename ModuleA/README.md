# Module A: Mini Database Engine with ACID Transactions

This project extends the B+ Tree based mini database to support ACID transactions, concurrency control, and crash recovery using a write-ahead log (WAL). The B+ Tree remains the sole storage structure for all tables, and every read/write goes through it.

## What Changed

- Added a transaction manager with WAL logging and recovery.
- Integrated begin/commit/rollback into the database manager.
- Made table writes transaction-aware and log undo/redo payloads.
- Adjusted B+ Tree mutators to return old values for undo.
- Added API endpoints for BEGIN/COMMIT/ROLLBACK.
- Added database-layer constraints (non-negative fields and references) enforced on insert/update.
- Added database-level isolation lock used for both transactions and reads.

## Key Files

- database/transaction.py: Transaction manager, WAL logging, recovery logic.
- database/db_manager.py: Transaction integration, recovery filtering, isolation lock.
- database/table.py: Transaction-aware insert/update/delete, constraints, recovery helpers.
- database/bplustree.py: Returns old values from insert/update/delete.
- routes.py: REST endpoints, including transaction routes.

## Transaction API Routes

- POST /transactions/begin -> { "tx_id": 1 }
- POST /transactions/commit with { "tx_id": 1 }
- POST /transactions/rollback with { "tx_id": 1 }

## Python Usage (In-Process)

```python
from database.db_manager import DatabaseManager

dbm = DatabaseManager()
dbm.create_database("TestDB")
dbm.create_table("TestDB", "Users", {"id": "int", "name": "str"}, order=4, search_key="id")
users = dbm.get_table("TestDB", "Users")

tx_id = dbm.begin()
users.insert({"id": 1, "name": "Ada"}, tx_id=tx_id)
users.update(1, {"id": 1, "name": "Ada Lovelace"}, tx_id=tx_id)
dbm.commit(tx_id)
```

If you omit tx_id in insert/update/delete, the table auto-creates and auto-commits a single-statement transaction.

## Table Constraints (Database Layer)

Constraints are enforced inside the database layer (Table.validate_record) and will raise ValueError on invalid data.
They can be passed when creating a table:

```python
constraints = {
	"non_negative": ["balance", "stock", "qty", "total"],
	"references": {
		"user_id": {"table": "Users", "key": "user_id"},
		"product_id": {"table": "Products", "key": "product_id"},
	},
}

dbm.create_table("ShopDB", "Orders", schema_orders, order=4, search_key="order_id", constraints=constraints)
```

Constraints currently implemented:

- Non-negative constraint: Enforced for any field listed in constraints["non_negative"].
	The value must be numeric (int/float) and $\ge 0$.
- Primary key constraint: The search key must be unique. Inserts that reuse an existing
	primary key are rejected. Updates cannot change the primary key value.
- Foreign key constraint: Enforced for any field listed in constraints["references"] or
	constraints["foreign_keys"].
	The value must exist as a key in the referenced table.

## WAL Format

Each log entry is a single line with a type prefix and JSON payload:

```
TX_START|{"type":"TX_START","tx_id":1}
TX_INSERT|{"type":"TX_INSERT","tx_id":1,"db":"TestDB","table":"Users","key":1,"old":null,"new":{"id":1,"name":"Ada"}}
TX_UPDATE|{"type":"TX_UPDATE","tx_id":1,"db":"TestDB","table":"Users","key":1,"old":{"id":1,"name":"Ada"},"new":{"id":1,"name":"Ada Lovelace"}}
TX_COMMIT|{"type":"TX_COMMIT","tx_id":1}
```

Log file: db_transactions.log (created in the ModuleA root).

## Recovery Logic (Crash Restart)

On DatabaseManager initialization, the WAL is parsed and replayed as follows:

1. Collect all TX_START and TX_COMMIT ids.
2. DatabaseManager filters WAL entries to only REDO committed transactions.
3. UNDO operations for transactions that started but never committed, in reverse order.
4. If a table is created after recovery runs, its queued redo/undo ops are applied when the table is created.

This ensures the B+ Tree ends in the exact state of the last committed transactions.

## ACID Principles: How They Are Enforced

- Atomicity: Every write is logged before it is applied (WAL). Each transaction keeps an in-memory list of its log entries, so rollback can undo changes in reverse order using the old values captured in the log. If commit cannot be logged, the manager immediately undoes all operations it already applied for that transaction.
- Consistency: The database enforces constraints (non-negative fields and reference checks) on insert/update. Recovery uses WAL redo/undo to restore a valid prior state, and invalid writes are rejected with ValueError.
- Isolation: A database-level isolation lock serializes transactions and is also used to guard read paths, preventing dirty reads and interleaved writes.
- Durability: Log writes are flushed and fsync'ed to db_transactions.log before a commit completes. On restart, recovery replays committed operations and undoes any uncommitted work to guarantee committed changes survive crashes.

## Testing: How It Was Tested

Test scripts are in the test folder:

- test/Atomicity.py (crash + verify)
- test/Consistency.py
- test/Isolation.py
- test/Durability.py
- test/multi_relation_transaction_demo.py

Run all tests from the ModuleA root in a global Python environment:

```powershell
$env:PYTHONPATH = (Get-Location).Path
py test/Atomicity.py --mode crash
py test/Atomicity.py --mode verify
py test/Consistency.py
py test/Isolation.py
py test/Durability.py
py test/multi_relation_transaction_demo.py --mode commit
```

## Test Results (Latest Run)

- Atomicity: PASS (rollback after simulated crash)
- Consistency: PASS (invalid writes rejected by database constraints)
- Isolation: PASS (serializable outcome)
- Durability: PASS
- Multi-relation demo: COMMIT applied; final state shows users balance 90, products stock 4, orders contains order_id 100

## Notes

- B+ Tree remains the only data store for each table. No external dictionaries are used for records.
- Table write methods return old values (or None) to support undo/redo logging.
- Graphviz is required only for visualize_tree; install it if you want rendering.
