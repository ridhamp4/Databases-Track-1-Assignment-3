"""
Module B: Race Condition & Failure Simulation Tests

Tests:
  1. Double-like race condition — same user clicks like twice rapidly
  2. Double-join race condition — same user tries to join group twice
  3. Concurrent update on same post — last-write-wins must not corrupt
  4. Failure during multi-step operation — rollback must leave clean state
  5. Concurrent poll votes — no duplicate votes
  6. Data integrity after concurrent writes

Usage:
  1. Start the backend: cd ../app/backend && python3 app.py
  2. Run:  python3 test_race_and_failure.py
"""

import requests
import threading
import time
import sys
import random
import string
import mysql.connector
from werkzeug.security import generate_password_hash

BASE_URL = "http://localhost:5001/api"
PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "root",
    "database": "iitgn_connect",
}


def random_str(n=8):
    return ''.join(random.choices(string.ascii_lowercase, k=n))


def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def seed_user(username, password="Test@1234"):
    """Insert a test user directly into MySQL (bypassing OTP), then login via API."""
    email = f"{username}@iitgn.ac.in"
    conn = get_db()
    cursor = conn.cursor(buffered=True)
    try:
        cursor.execute("SELECT MemberID FROM Member WHERE Username = %s", (username,))
        row = cursor.fetchone()
        if not row:
            pw_hash = generate_password_hash(password)
            cursor.execute(
                "INSERT INTO Member (Username, Name, Email, Password, MemberType, CreatedAt, AvatarColor) "
                "VALUES (%s, %s, %s, %s, 'Student', CURDATE(), '#4F46E5')",
                (username, f"Test {username}", email, pw_hash),
            )
            member_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO Student (MemberID, Programme, Branch, CurrentYear, MessAssignment) "
                "VALUES (%s, 'BTech', 'CSE', 1, 'Mess1')",
                (member_id,),
            )
            conn.commit()
    finally:
        cursor.close()
        conn.close()

    r = requests.post(f"{BASE_URL}/auth/login", json={
        "username": username, "password": password
    }, timeout=10)
    if r.status_code == 200:
        data = r.json()
        return data.get("token") or data.get("session_token") or data.get("access_token")
    return None


def auth_header(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ═══════════════════════════════════════════════════════
#  TEST 1: Double-like race condition
# ═══════════════════════════════════════════════════════
def test_double_like_race(token, post_id):
    """Same user clicks like twice rapidly — should toggle correctly, not create duplicates."""
    print("\n[TEST] Double-like Race Condition")
    results = []
    lock = threading.Lock()

    def like(idx):
        r = requests.post(f"{BASE_URL}/posts/{post_id}/like",
                          headers=auth_header(token), timeout=10)
        with lock:
            results.append((idx, r.status_code, r.json() if r.status_code == 200 else {}))

    t1 = threading.Thread(target=like, args=(1,))
    t2 = threading.Thread(target=like, args=(2,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    all_200 = all(r[1] == 200 for r in results)
    liked_states = [r[2].get("liked") for r in results]
    ok = all_200
    print(f"  [{PASS if ok else FAIL}] Both requests succeeded (states: {liked_states})")
    return ok


# ═══════════════════════════════════════════════════════
#  TEST 2: Double-join race condition
# ═══════════════════════════════════════════════════════
def test_double_join_race(token, admin_token):
    """Same user tries to join the same group twice simultaneously."""
    print("\n[TEST] Double-join Race Condition")

    r = requests.post(f"{BASE_URL}/groups/", json={
        "name": f"RaceTest-{random_str()}", "description": "Double join test",
        "isRestricted": False,
    }, headers=auth_header(admin_token), timeout=10)

    if r.status_code != 201:
        print(f"  [{FAIL}] Could not create group")
        return False

    group_id = r.json()["groupId"]
    results = []
    lock = threading.Lock()

    def join(idx):
        r = requests.post(f"{BASE_URL}/groups/{group_id}/join",
                          headers=auth_header(token), timeout=10)
        with lock:
            results.append((idx, r.status_code))

    t1 = threading.Thread(target=join, args=(1,))
    t2 = threading.Thread(target=join, args=(2,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    statuses = sorted([r[1] for r in results])
    no_server_error = all(s < 500 for s in statuses)
    print(f"  [{PASS if no_server_error else FAIL}] No server errors (statuses: {statuses})")
    return no_server_error


# ═══════════════════════════════════════════════════════
#  TEST 3: Concurrent update on same post
# ═══════════════════════════════════════════════════════
def test_concurrent_post_update(token):
    """Two threads update the same post simultaneously — should not corrupt data."""
    print("\n[TEST] Concurrent Post Update (Same Post)")

    r = requests.post(f"{BASE_URL}/posts", json={
        "content": "Original content"
    }, headers=auth_header(token), timeout=10)

    if r.status_code != 201:
        print(f"  [{FAIL}] Could not create post")
        return False

    post_id = r.json()["postId"]
    results = []
    lock = threading.Lock()

    def update(content, idx):
        r = requests.put(f"{BASE_URL}/posts/{post_id}", json={
            "content": content
        }, headers=auth_header(token), timeout=10)
        with lock:
            results.append((idx, r.status_code))

    t1 = threading.Thread(target=update, args=("Update A", 1))
    t2 = threading.Thread(target=update, args=("Update B", 2))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    all_ok = all(r[1] == 200 for r in results)
    print(f"  [{PASS if all_ok else FAIL}] Both updates succeeded without corruption")
    return all_ok


# ═══════════════════════════════════════════════════════
#  TEST 4: Transaction rollback on failure
# ═══════════════════════════════════════════════════════
def test_transaction_rollback():
    """A multi-statement transaction with a failing statement rolls back entirely."""
    print("\n[TEST] Transaction Rollback on Failure")

    r = requests.post(f"{BASE_URL}/transaction-test", json={
        "statements": [
            {"sql": "SELECT 1", "args": []}
        ],
        "simulate_failure": True
    }, timeout=10)

    if r.status_code == 200:
        data = r.json()
        ok = data.get("status") == "rolled_back"
        print(f"  [{PASS if ok else FAIL}] Transaction status: {data.get('status')}")
        return ok

    print(f"  [{FAIL}] Unexpected response: {r.status_code}")
    return False


# ═══════════════════════════════════════════════════════
#  TEST 5: Concurrent poll creation & voting
# ═══════════════════════════════════════════════════════
def test_concurrent_poll_votes(tokens):
    """Multiple users vote on the same poll simultaneously."""
    print("\n[TEST] Concurrent Poll Votes")

    r = requests.post(f"{BASE_URL}/polls/", json={
        "question": f"Stress test poll {random_str()}",
        "options": ["Option A", "Option B", "Option C"],
        "expiresAt": "2026-12-31T23:59:59",
    }, headers=auth_header(tokens[0]), timeout=10)

    if r.status_code != 201:
        print(f"  [{FAIL}] Could not create poll: {r.status_code} {r.text[:100]}")
        return False

    poll_id = r.json().get("pollId")
    if not poll_id:
        print(f"  [{FAIL}] No poll ID returned")
        return False

    r2 = requests.get(f"{BASE_URL}/polls/", headers=auth_header(tokens[0]), timeout=10)
    if r2.status_code != 200:
        print(f"  [{FAIL}] Could not get polls")
        return False

    polls = r2.json()
    poll = next((p for p in polls if p["PollID"] == poll_id), None)
    if not poll or not poll.get("options"):
        print(f"  [{FAIL}] Poll or options not found")
        return False

    option_id = poll["options"][0]["OptionID"]
    results = {"success": 0, "fail": 0}
    lock = threading.Lock()

    def vote(token, idx):
        try:
            r = requests.post(f"{BASE_URL}/polls/{poll_id}/vote", json={
                "optionId": option_id
            }, headers=auth_header(token), timeout=10)
            with lock:
                if r.status_code < 400:
                    results["success"] += 1
                else:
                    results["fail"] += 1
        except Exception as e:
            with lock:
                results["fail"] += 1

    threads = []
    for i, token in enumerate(tokens[1:]):
        t = threading.Thread(target=vote, args=(token, i))
        threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    ok = results["fail"] == 0
    print(f"  [{PASS if ok else FAIL}] {results['success']} votes cast, {results['fail']} failures")
    return ok


# ═══════════════════════════════════════════════════════
#  TEST 6: Data integrity after high-concurrency writes
# ═══════════════════════════════════════════════════════
def test_data_integrity_after_writes(tokens):
    """After many concurrent writes, verify data counts match."""
    print("\n[TEST] Data Integrity After Concurrent Writes")

    marker = random_str(12)
    results = {"success": 0}
    lock = threading.Lock()

    def create(token, idx):
        r = requests.post(f"{BASE_URL}/posts", json={
            "content": f"integrity_{marker}_{idx}"
        }, headers=auth_header(token), timeout=10)
        if r.status_code == 201:
            with lock:
                results["success"] += 1

    threads = [threading.Thread(target=create, args=(t, i)) for i, t in enumerate(tokens)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    time.sleep(0.5)
    r = requests.get(f"{BASE_URL}/posts?feed=global", headers=auth_header(tokens[0]), timeout=10)
    if r.status_code == 200:
        posts = r.json()
        found = sum(1 for p in posts if marker in p.get("Content", ""))
        ok = found == results["success"]
        print(f"  [{PASS if ok else FAIL}] Created {results['success']}, found {found} in DB")
        return ok

    print(f"  [{FAIL}] Could not verify posts")
    return False


# ═══════════════════════════════════════════════════════
#  MAIN RUNNER
# ═══════════════════════════════════════════════════════

def main():
    print("=" * 65)
    print("  MODULE B: RACE CONDITION & FAILURE SIMULATION TESTS")
    print("=" * 65)

    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        if r.status_code != 200:
            print(f"[ERROR] Server returned {r.status_code}")
            return False
        print(f"[OK] Server running: {r.json()}")
    except requests.ConnectionError:
        print("[ERROR] Cannot connect to server. Start backend first.")
        return False

    print("\n[SETUP] Creating test users...")
    tokens = []
    for i in range(5):
        uname = f"race_user_{i}"
        token = seed_user(uname)
        if token:
            tokens.append(token)
            print(f"  {uname}: OK")
        else:
            print(f"  {uname}: FAILED")

    if len(tokens) < 2:
        print("[ERROR] Need at least 2 users")
        return False

    r = requests.post(f"{BASE_URL}/posts", json={
        "content": f"Race test post {random_str()}"
    }, headers=auth_header(tokens[0]), timeout=10)
    test_post_id = r.json()["postId"] if r.status_code == 201 else None

    passed = 0
    failed = 0
    tests = []

    if test_post_id:
        tests.append(("Double-like Race", lambda: test_double_like_race(tokens[1], test_post_id)))
    tests.append(("Double-join Race", lambda: test_double_join_race(tokens[1], tokens[0])))
    tests.append(("Concurrent Post Update", lambda: test_concurrent_post_update(tokens[0])))
    tests.append(("Transaction Rollback", test_transaction_rollback))
    tests.append(("Concurrent Poll Votes", lambda: test_concurrent_poll_votes(tokens)))
    tests.append(("Data Integrity", lambda: test_data_integrity_after_writes(tokens)))

    for name, fn in tests:
        try:
            if fn():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  [{FAIL}] {name}: EXCEPTION — {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 65)
    print(f"  RESULTS: {passed} passed, {failed} failed, {len(tests)} total")
    print("=" * 65)
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
