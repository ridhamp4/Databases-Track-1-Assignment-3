# Module A: Mini Database Engine with ACID Transactions

This project extends the B+ Tree based mini database to support ACID transactions, concurrency control, and crash recovery using a write-ahead log (WAL). The B+ Tree remains the sole storage structure for all tables, and every read/write goes through it.

## What Changed

- Added a transaction manager with WAL logging and recovery.
- Integrated begin/commit/rollback into the database manager.
- Made table writes transaction-aware and log undo/redo payloads.
- Adjusted B+ Tree mutators to return old values for undo.
- Added API endpoints for BEGIN/COMMIT/ROLLBACK.

## Key Files

- database/transaction.py: Transaction manager, WAL logging, recovery logic.
- database/db_manager.py: Transaction integration and recovery apply hooks.
- database/table.py: Transaction-aware insert/update/delete plus recovery helpers.
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
2. REDO all operations from committed transactions in log order.
3. UNDO all operations from transactions that started but never committed, in reverse order.
4. If a table is created after recovery runs, its queued redo/undo ops are applied when the table is created.

This ensures the B+ Tree ends in the exact state of the last committed transactions.

## ACID Principles: How They Are Enforced

- Atomicity: Every write is logged before it is applied (WAL). Each transaction keeps an in-memory list of its log entries, so rollback can undo changes in reverse order using the old values captured in the log. If commit cannot be logged, the manager immediately undoes all operations it already applied for that transaction.
- Consistency: The B+ Tree is always restored to a valid prior state because each log entry includes enough information to deterministically restore the exact old record or reapply the new record. Rollback uses the stored old values, and recovery applies committed entries in order, then undoes any partial entries in reverse order.
- Isolation: A global transaction lock serializes transactions. This is a strict two-phase locking style because the lock is held from begin through commit/rollback, preventing interleaved writes and making transaction behavior equivalent to serial execution.
- Durability: Log writes are flushed and fsync'ed to db_transactions.log before a commit completes. On restart, recovery replays committed operations and undoes any uncommitted work to guarantee committed changes survive crashes.

## Notes

- B+ Tree remains the only data store for each table. No external dictionaries are used for records.
- Table write methods return old values (or None) to support undo/redo logging.
- Graphviz is required only for visualize_tree; install it if you want rendering.
