# ACID Test Suite README

This folder contains the ACID validation tests and the multi-relation transaction demo.

If running in a global Python environment, set PYTHONPATH to the ModuleA root first:

```powershell
$env:PYTHONPATH = (Get-Location).Path
```

## Atomicity Test

Goal: Verify that a multi-table transaction either completes fully or is fully rolled back after a crash.

Steps:
1. Run the crash phase (writes without commit):
   - python test/Atomicity.py --mode crash
2. Restart and verify state:
   - python test/Atomicity.py --mode verify

Expected Result:
- Users balance remains 100.
- Products stock remains 5.
- Orders table does not contain order_id 100.

Notes:
- The crash is simulated by exiting the process after the writes, with no commit/rollback.
- Recovery should UNDO all uncommitted WAL entries on the next startup.

## Consistency Test

Goal: Ensure all relations remain valid after operations.

Constraints Checked:
- User balance is non-negative.
- Product stock and price are non-negative.
- Primary key uniqueness on search keys.
- Orders reference existing users and products.

How to Run:
- python test/Consistency.py

Expected Result:
- The script prints PASS and returns exit code 0.
- It reports expected failures when attempting invalid writes (negative stock, negative balance, invalid references).

Notes:
- These checks are enforced in the database layer (Table.validate_record). Invalid writes raise ValueError and are rolled back.
- Primary key constraints reject duplicate inserts and prevent changing the search key on update.

## Isolation Test

Goal: Execute concurrent transactions on shared data and verify no corruption or lost updates.

How to Run:
- python test/Isolation.py

Expected Result:
- Final balance is 80 (two serialized decrements of 10). The script prints PASS and exits 0.

Notes:
- Isolation is enforced by a database-level lock held from BEGIN through COMMIT/ROLLBACK.
- Reads are also guarded by the same lock to avoid dirty reads.

## Durability Test

Goal: Verify committed data persists after a restart and recovery.

How to Run:
- python test/Durability.py

Expected Result:
- The script prints PASS and exits 0, confirming recovery restores committed data.

Notes:
- The test simulates a restart by creating a new DatabaseManager instance in the same process.
- WAL entries are fsync'ed before commit completes, and recovery replays committed entries.

## Multi-Relation Transaction Demo

Goal: Demonstrate a single transaction spanning at least three relations (Users, Products, Orders).

How to Run:
- python test/multi_relation_transaction_demo.py --mode commit
- python test/multi_relation_transaction_demo.py --mode rollback
- python test/multi_relation_transaction_demo.py --mode crash
- python test/multi_relation_transaction_demo.py --mode verify

Expected Result (commit mode):
- Users balance decreases by 10 (from 100 to 90).
- Products stock decreases by 1 (from 5 to 4).
- Orders contains order_id 100.

Expected Result (rollback or crash + verify):
- Users balance remains 100.
- Products stock remains 5.
- Orders does not contain order_id 100.

Notes:
- Constraints are enforced at the database layer (non-negative fields and reference checks).
- Crash mode simulates a failure by exiting after writes with no commit/rollback; verify shows recovery results.
- The demo uses a dedicated WAL file test/multi_relation.log and resets it for commit/rollback/crash runs.
