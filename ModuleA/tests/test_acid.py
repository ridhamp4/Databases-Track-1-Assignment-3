"""
ACID Validation Tests for B+ Tree Transaction Engine.

Tests:
  1. Atomicity   — transaction either fully commits or fully rolls back
  2. Consistency — data remains valid after every operation
  3. Isolation   — concurrent transactions do not interfere
  4. Durability  — committed data survives crash recovery
"""

import sys
import os
import shutil
import threading
import time
import copy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database.db_manager import DatabaseManager
from database.transaction_manager import TransactionManager

WAL_DIR = os.path.join(os.path.dirname(__file__), 'test_wal_logs')

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"


def setup():
    """Create a fresh DB manager and transaction manager."""
    if os.path.exists(WAL_DIR):
        shutil.rmtree(WAL_DIR)
    db = DatabaseManager()
    db.create_database("testdb")
    db.create_table("testdb", "users", {"id": "int", "name": "str", "balance": "int"}, 8, "id")
    tm = TransactionManager(db, wal_dir=WAL_DIR)
    return db, tm


def teardown():
    if os.path.exists(WAL_DIR):
        shutil.rmtree(WAL_DIR)


# ═══════════════════════════════════════════════
#  TEST 1: ATOMICITY — Commit
# ═══════════════════════════════════════════════
def test_atomicity_commit():
    """A committed transaction's changes must persist."""
    db, tm = setup()
    table = db.get_table("testdb", "users")

    txn = tm.begin()
    tm.insert(txn, "testdb", "users", {"id": 1, "name": "Alice", "balance": 1000})
    tm.insert(txn, "testdb", "users", {"id": 2, "name": "Bob", "balance": 2000})
    tm.commit(txn)

    r1 = table.get(1)
    r2 = table.get(2)
    ok = r1 is not None and r2 is not None and r1["name"] == "Alice" and r2["name"] == "Bob"
    print(f"  [{'PASS' if ok else 'FAIL'}] Atomicity (commit): both records exist after commit")
    teardown()
    return ok


# ═══════════════════════════════════════════════
#  TEST 2: ATOMICITY — Rollback
# ═══════════════════════════════════════════════
def test_atomicity_rollback():
    """A rolled-back transaction's changes must be undone."""
    db, tm = setup()
    table = db.get_table("testdb", "users")

    # Insert a baseline record via committed transaction
    txn1 = tm.begin()
    tm.insert(txn1, "testdb", "users", {"id": 1, "name": "Alice", "balance": 1000})
    tm.commit(txn1)

    # Start another transaction that modifies and adds
    txn2 = tm.begin()
    tm.update(txn2, "testdb", "users", 1, {"id": 1, "name": "Alice", "balance": 500})
    tm.insert(txn2, "testdb", "users", {"id": 2, "name": "Bob", "balance": 2000})
    tm.rollback(txn2)

    r1 = table.get(1)
    r2 = table.get(2)
    ok = (r1 is not None and r1["balance"] == 1000 and r2 is None)
    print(f"  [{'PASS' if ok else 'FAIL'}] Atomicity (rollback): changes undone after rollback")
    teardown()
    return ok


# ═══════════════════════════════════════════════
#  TEST 3: ATOMICITY — Simulated failure mid-transaction
# ═══════════════════════════════════════════════
def test_atomicity_failure():
    """If a transaction fails mid-way, partial changes are rolled back."""
    db, tm = setup()
    table = db.get_table("testdb", "users")

    txn = tm.begin()
    tm.insert(txn, "testdb", "users", {"id": 1, "name": "Alice", "balance": 1000})

    # Simulate failure: try inserting invalid record, then rollback
    try:
        tm.insert(txn, "testdb", "users", {"id": 1, "name": "Duplicate", "balance": 0})
    except ValueError:
        pass  # Expected: duplicate key

    # Rollback the entire transaction
    tm.rollback(txn)

    r1 = table.get(1)
    ok = r1 is None
    print(f"  [{'PASS' if ok else 'FAIL'}] Atomicity (failure): partial insert rolled back on error")
    teardown()
    return ok


# ═══════════════════════════════════════════════
#  TEST 4: CONSISTENCY — Balance transfer
# ═══════════════════════════════════════════════
def test_consistency_transfer():
    """Total balance must remain constant after a transfer."""
    db, tm = setup()
    table = db.get_table("testdb", "users")

    # Setup
    txn1 = tm.begin()
    tm.insert(txn1, "testdb", "users", {"id": 1, "name": "Alice", "balance": 1000})
    tm.insert(txn1, "testdb", "users", {"id": 2, "name": "Bob", "balance": 1000})
    tm.commit(txn1)

    total_before = table.get(1)["balance"] + table.get(2)["balance"]

    # Transfer 300 from Alice to Bob
    txn2 = tm.begin()
    tm.update(txn2, "testdb", "users", 1, {"id": 1, "name": "Alice", "balance": 700})
    tm.update(txn2, "testdb", "users", 2, {"id": 2, "name": "Bob", "balance": 1300})
    tm.commit(txn2)

    total_after = table.get(1)["balance"] + table.get(2)["balance"]
    ok = total_before == total_after == 2000
    print(f"  [{'PASS' if ok else 'FAIL'}] Consistency: total balance preserved ({total_before} -> {total_after})")
    teardown()
    return ok


# ═══════════════════════════════════════════════
#  TEST 5: CONSISTENCY — Rollback preserves invariants
# ═══════════════════════════════════════════════
def test_consistency_rollback():
    """After rollback, data should match pre-transaction state."""
    db, tm = setup()
    table = db.get_table("testdb", "users")

    txn1 = tm.begin()
    tm.insert(txn1, "testdb", "users", {"id": 1, "name": "Alice", "balance": 1000})
    tm.commit(txn1)

    snapshot_before = copy.deepcopy(table.get(1))

    txn2 = tm.begin()
    tm.update(txn2, "testdb", "users", 1, {"id": 1, "name": "Alice", "balance": 0})
    tm.rollback(txn2)

    snapshot_after = table.get(1)
    ok = snapshot_before == snapshot_after
    print(f"  [{'PASS' if ok else 'FAIL'}] Consistency (rollback): data matches pre-txn state")
    teardown()
    return ok


# ═══════════════════════════════════════════════
#  TEST 6: ISOLATION — Concurrent transactions
# ═══════════════════════════════════════════════
def test_isolation_concurrent():
    """Two concurrent transactions should not interfere with each other."""
    db, tm = setup()
    table = db.get_table("testdb", "users")

    # Setup initial data
    txn_setup = tm.begin()
    tm.insert(txn_setup, "testdb", "users", {"id": 1, "name": "Alice", "balance": 1000})
    tm.insert(txn_setup, "testdb", "users", {"id": 2, "name": "Bob", "balance": 1000})
    tm.commit(txn_setup)

    errors = []

    def txn_a():
        try:
            t = tm.begin()
            tm.update(t, "testdb", "users", 1, {"id": 1, "name": "Alice", "balance": 800})
            time.sleep(0.05)  # simulate delay
            tm.commit(t)
        except Exception as e:
            errors.append(f"TxnA: {e}")

    def txn_b():
        try:
            t = tm.begin()
            tm.update(t, "testdb", "users", 2, {"id": 2, "name": "Bob", "balance": 1200})
            time.sleep(0.05)
            tm.commit(t)
        except Exception as e:
            errors.append(f"TxnB: {e}")

    t1 = threading.Thread(target=txn_a)
    t2 = threading.Thread(target=txn_b)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    r1 = table.get(1)
    r2 = table.get(2)
    ok = (len(errors) == 0 and
          r1["balance"] == 800 and r2["balance"] == 1200)
    print(f"  [{'PASS' if ok else 'FAIL'}] Isolation: concurrent txns on different keys work independently")
    if errors:
        for e in errors:
            print(f"    Error: {e}")
    teardown()
    return ok


# ═══════════════════════════════════════════════
#  TEST 7: DURABILITY — WAL recovery after commit
# ═══════════════════════════════════════════════
def test_durability_recovery():
    """Committed data should be recoverable after a simulated crash."""
    db, tm = setup()

    # Commit some data
    txn1 = tm.begin()
    tm.insert(txn1, "testdb", "users", {"id": 1, "name": "Alice", "balance": 1000})
    tm.insert(txn1, "testdb", "users", {"id": 2, "name": "Bob", "balance": 2000})
    tm.commit(txn1)

    # Simulate crash: create new DB manager (empty state) but keep WAL
    db2 = DatabaseManager()
    db2.create_database("testdb")
    db2.create_table("testdb", "users", {"id": "int", "name": "str", "balance": "int"}, 8, "id")
    tm2 = TransactionManager(db2, wal_dir=WAL_DIR)

    # Recover from WAL
    report = tm2.recover()

    table2 = db2.get_table("testdb", "users")
    r1 = table2.get(1)
    r2 = table2.get(2)
    ok = (r1 is not None and r1["name"] == "Alice" and r1["balance"] == 1000 and
          r2 is not None and r2["name"] == "Bob" and r2["balance"] == 2000)
    print(f"  [{'PASS' if ok else 'FAIL'}] Durability: committed data recovered after crash (redo={report['redo_count']})")
    teardown()
    return ok


# ═══════════════════════════════════════════════
#  TEST 8: DURABILITY — Uncommitted data NOT recovered
# ═══════════════════════════════════════════════
def test_durability_uncommitted_not_recovered():
    """Uncommitted data should NOT appear after recovery."""
    db, tm = setup()

    # Commit one record
    txn1 = tm.begin()
    tm.insert(txn1, "testdb", "users", {"id": 1, "name": "Alice", "balance": 1000})
    tm.commit(txn1)

    # Start another transaction but do NOT commit
    txn2 = tm.begin()
    tm.insert(txn2, "testdb", "users", {"id": 2, "name": "Bob", "balance": 2000})
    # (crash here — no commit)

    # Simulate crash
    db2 = DatabaseManager()
    db2.create_database("testdb")
    db2.create_table("testdb", "users", {"id": "int", "name": "str", "balance": "int"}, 8, "id")
    tm2 = TransactionManager(db2, wal_dir=WAL_DIR)
    report = tm2.recover()

    table2 = db2.get_table("testdb", "users")
    r1 = table2.get(1)
    r2 = table2.get(2)
    ok = (r1 is not None and r1["name"] == "Alice" and r2 is None)
    print(f"  [{'PASS' if ok else 'FAIL'}] Durability: uncommitted data NOT present after recovery (undo={report['undo_count']})")
    teardown()
    return ok


# ═══════════════════════════════════════════════
#  TEST 9: CHECKPOINT — Snapshot + Recovery
# ═══════════════════════════════════════════════
def test_checkpoint_recovery():
    """After checkpoint, recovery should restore from snapshot."""
    db, tm = setup()

    # Insert and commit
    txn1 = tm.begin()
    tm.insert(txn1, "testdb", "users", {"id": 1, "name": "Alice", "balance": 1000})
    tm.commit(txn1)

    # Checkpoint
    tm.checkpoint()

    # More operations after checkpoint
    txn2 = tm.begin()
    tm.insert(txn2, "testdb", "users", {"id": 2, "name": "Bob", "balance": 2000})
    tm.commit(txn2)

    # Simulate crash
    db2 = DatabaseManager()
    tm2 = TransactionManager(db2, wal_dir=WAL_DIR)
    report = tm2.recover()

    table2 = db2.get_table("testdb", "users")
    r1 = table2.get(1)
    r2 = table2.get(2)

    ok = (report["checkpoint_loaded"] and
          r1 is not None and r1["name"] == "Alice" and
          r2 is not None and r2["name"] == "Bob")
    print(f"  [{'PASS' if ok else 'FAIL'}] Checkpoint: snapshot + post-checkpoint ops recovered")
    teardown()
    return ok


# ═══════════════════════════════════════════════
#  TEST 10: B+ Tree + DB Consistency
# ═══════════════════════════════════════════════
def test_btree_db_consistency():
    """B+ Tree index and table data must always match."""
    db, tm = setup()
    table = db.get_table("testdb", "users")

    txn1 = tm.begin()
    for i in range(1, 21):
        tm.insert(txn1, "testdb", "users", {"id": i, "name": f"User{i}", "balance": i * 100})
    tm.commit(txn1)

    # Verify all records exist in B+ tree
    all_records = table.get_all()
    all_ok = len(all_records) == 20
    for i in range(1, 21):
        r = table.get(i)
        if r is None or r["id"] != i:
            all_ok = False
            break

    # Delete some via transaction
    txn2 = tm.begin()
    for i in [5, 10, 15]:
        tm.delete(txn2, "testdb", "users", i)
    tm.commit(txn2)

    remaining = table.get_all()
    remaining_ok = len(remaining) == 17
    for i in [5, 10, 15]:
        if table.get(i) is not None:
            remaining_ok = False

    ok = all_ok and remaining_ok
    print(f"  [{'PASS' if ok else 'FAIL'}] B+ Tree consistency: index matches data after insert+delete")
    teardown()
    return ok


# ═══════════════════════════════════════════════
#  TEST 11: WAL Logging verification
# ═══════════════════════════════════════════════
def test_wal_logging():
    """WAL must contain entries for all operations."""
    db, tm = setup()

    txn = tm.begin()
    tm.insert(txn, "testdb", "users", {"id": 1, "name": "Alice", "balance": 1000})
    tm.update(txn, "testdb", "users", 1, {"id": 1, "name": "Alice", "balance": 800})
    tm.delete(txn, "testdb", "users", 1)
    tm.commit(txn)

    entries = tm.get_wal_entries()
    ops = [e["op"] for e in entries]
    ok = ("BEGIN" in ops and "INSERT" in ops and "UPDATE" in ops and
          "DELETE" in ops and "COMMIT" in ops)
    print(f"  [{'PASS' if ok else 'FAIL'}] WAL logging: all operations recorded ({len(entries)} entries)")
    teardown()
    return ok


# ═══════════════════════════════════════════════
#  RUNNER
# ═══════════════════════════════════════════════
def main():
    print("=" * 60)
    print("  ACID VALIDATION TESTS — B+ Tree Transaction Engine")
    print("=" * 60)

    tests = [
        ("Atomicity — Commit", test_atomicity_commit),
        ("Atomicity — Rollback", test_atomicity_rollback),
        ("Atomicity — Failure mid-txn", test_atomicity_failure),
        ("Consistency — Balance transfer", test_consistency_transfer),
        ("Consistency — Rollback preserves state", test_consistency_rollback),
        ("Isolation — Concurrent transactions", test_isolation_concurrent),
        ("Durability — WAL recovery (committed)", test_durability_recovery),
        ("Durability — Uncommitted not recovered", test_durability_uncommitted_not_recovered),
        ("Checkpoint — Snapshot + recovery", test_checkpoint_recovery),
        ("B+ Tree/DB consistency", test_btree_db_consistency),
        ("WAL logging verification", test_wal_logging),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        print(f"\n[TEST] {name}")
        try:
            if fn():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  [{FAIL}] {name}: EXCEPTION — {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"  RESULTS: {passed} passed, {failed} failed, {len(tests)} total")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
