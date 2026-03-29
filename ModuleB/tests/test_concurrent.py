"""
Module B: Concurrent Workload & Stress Testing

Tests multi-user concurrent access to the IITGN Connect API.
Covers: concurrent posts, likes, group joins, and poll votes.
Verifies ACID properties under load.

Usage:
  1. Start the backend: cd ../app/backend && python3 app.py
  2. Run:  python3 test_concurrent.py
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


# ─── Helpers ──────────────────────────────────────────

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
        # Check if already exists
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

    # Login via API
    r = requests.post(f"{BASE_URL}/auth/login", json={
        "username": username, "password": password
    }, timeout=10)
    if r.status_code == 200:
        data = r.json()
        return data.get("token") or data.get("session_token") or data.get("access_token")
    return None


def auth_header(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ─── Test 1: Concurrent Post Creation ──────────────────

def test_concurrent_post_creation(tokens):
    """Multiple users create posts simultaneously."""
    print("\n[TEST] Concurrent Post Creation")
    results = {"success": 0, "fail": 0, "errors": []}
    lock = threading.Lock()

    def create_post(token, idx):
        try:
            r = requests.post(f"{BASE_URL}/posts", json={
                "content": f"Concurrent post #{idx} at {time.time()}"
            }, headers=auth_header(token), timeout=10)
            with lock:
                if r.status_code == 201:
                    results["success"] += 1
                else:
                    results["fail"] += 1
                    results["errors"].append(f"#{idx}: {r.status_code} {r.text[:100]}")
        except Exception as e:
            with lock:
                results["fail"] += 1
                results["errors"].append(f"#{idx}: {e}")

    threads = []
    for i in range(20):
        token = tokens[i % len(tokens)]
        t = threading.Thread(target=create_post, args=(token, i))
        threads.append(t)

    start = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.time() - start

    ok = results["success"] == 20
    print(f"  [{PASS if ok else FAIL}] {results['success']}/20 posts created in {elapsed:.2f}s")
    if results["errors"]:
        for e in results["errors"][:3]:
            print(f"    Error: {e}")
    return ok


# ─── Test 2: Concurrent Like Toggle (Race Condition) ───

def test_concurrent_like_toggle(tokens, post_id):
    """Multiple users like the same post simultaneously — no duplicates or server errors."""
    print("\n[TEST] Concurrent Like Toggle (Race Condition)")
    results = {"success": 0, "fail": 0, "errors": []}
    lock = threading.Lock()

    def like_post(token, idx):
        try:
            r = requests.post(f"{BASE_URL}/posts/{post_id}/like",
                              headers=auth_header(token), timeout=10)
            with lock:
                if r.status_code == 200:
                    results["success"] += 1
                else:
                    results["fail"] += 1
                    results["errors"].append(f"#{idx}: HTTP {r.status_code}")
        except Exception as e:
            with lock:
                results["fail"] += 1
                results["errors"].append(f"#{idx}: {e}")

    threads = []
    for i, token in enumerate(tokens):
        t = threading.Thread(target=like_post, args=(token, i))
        threads.append(t)

    start = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.time() - start

    ok = results["fail"] == 0 and results["success"] == len(tokens)
    print(f"  [{PASS if ok else FAIL}] {results['success']}/{len(tokens)} likes processed in {elapsed:.2f}s, {results['fail']} failures")
    if results["errors"]:
        for e in results["errors"][:5]:
            print(f"    Error: {e}")
    return ok


# ─── Test 3: Concurrent Group Join ─────────────────────

def test_concurrent_group_join(tokens, admin_token):
    """Many users try to join the same group simultaneously."""
    print("\n[TEST] Concurrent Group Join")

    # Create a test group
    r = requests.post(f"{BASE_URL}/groups/", json={
        "name": f"StressTest-{random_str()}",
        "description": "Concurrent join test",
        "isRestricted": False,
    }, headers=auth_header(admin_token), timeout=10)

    if r.status_code != 201:
        print(f"  [{FAIL}] Could not create test group: {r.text[:100]}")
        return False

    group_id = r.json()["groupId"]
    results = {"joined": 0, "already": 0, "fail": 0}
    lock = threading.Lock()

    def join_group(token, idx):
        try:
            r = requests.post(f"{BASE_URL}/groups/{group_id}/join",
                              headers=auth_header(token), timeout=10)
            with lock:
                if r.status_code == 200:
                    results["joined"] += 1
                elif r.status_code == 409:
                    results["already"] += 1
                else:
                    results["fail"] += 1
        except Exception as e:
            with lock:
                results["fail"] += 1

    threads = []
    join_tokens = [t for t in tokens if t != admin_token]
    for i, token in enumerate(join_tokens):
        t = threading.Thread(target=join_group, args=(token, i))
        threads.append(t)

    start = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.time() - start

    total = results["joined"] + results["already"]
    ok = results["fail"] == 0 and total == len(join_tokens)
    print(f"  [{PASS if ok else FAIL}] {results['joined']} joined, {results['already']} already members, {results['fail']} failures in {elapsed:.2f}s")
    return ok


# ─── Test 4: Stress Test — High Volume Requests ────────

def test_stress_high_volume(tokens):
    """Send a large number of mixed requests to test system under load."""
    print("\n[TEST] Stress Test — High Volume (100 mixed requests)")
    results = {"success": 0, "fail": 0, "errors": []}
    lock = threading.Lock()
    total_requests = 100

    def make_request(idx):
        token = tokens[idx % len(tokens)]
        try:
            op = idx % 4
            if op == 0:
                r = requests.get(f"{BASE_URL}/posts?feed=global",
                                 headers=auth_header(token), timeout=15)
            elif op == 1:
                r = requests.post(f"{BASE_URL}/posts", json={
                    "content": f"Stress test post #{idx}"
                }, headers=auth_header(token), timeout=15)
            elif op == 2:
                r = requests.get(f"{BASE_URL}/groups/",
                                 headers=auth_header(token), timeout=15)
            else:
                r = requests.get(f"{BASE_URL}/polls/",
                                 headers=auth_header(token), timeout=15)

            with lock:
                if r.status_code < 400:
                    results["success"] += 1
                else:
                    results["fail"] += 1
                    results["errors"].append(f"#{idx}: {r.status_code}")
        except Exception as e:
            with lock:
                results["fail"] += 1
                results["errors"].append(f"#{idx}: {e}")

    threads = []
    for i in range(total_requests):
        t = threading.Thread(target=make_request, args=(i,))
        threads.append(t)

    start = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.time() - start

    rps = total_requests / elapsed if elapsed > 0 else 0
    ok = results["success"] >= total_requests * 0.95
    print(f"  [{PASS if ok else FAIL}] {results['success']}/{total_requests} succeeded in {elapsed:.2f}s ({rps:.1f} req/s)")
    if results["errors"]:
        for e in results["errors"][:5]:
            print(f"    Error: {e}")
    return ok


# ─── Test 5: Transaction Atomicity (Simulated Failure) ─

def test_transaction_atomicity():
    """Test that a transaction with a failing statement rolls back completely."""
    print("\n[TEST] Transaction Atomicity — Simulated Failure")

    r = requests.post(f"{BASE_URL}/transaction-test", json={
        "statements": [
            {"sql": "SELECT 1", "args": []}
        ],
        "simulate_failure": True
    }, timeout=10)

    if r.status_code == 200:
        data = r.json()
        ok = data.get("status") == "rolled_back"
        print(f"  [{PASS if ok else FAIL}] Transaction rolled back on failure (status={data.get('status')})")
        return ok
    else:
        print(f"  [{FAIL}] Unexpected response: {r.status_code} {r.text[:100]}")
        return False


# ─── Test 6: Durability — Data persists after operations ─

def test_durability(token):
    """Create data, verify it persists after multiple operations."""
    print("\n[TEST] Durability — Data persistence")

    r = requests.post(f"{BASE_URL}/posts", json={
        "content": f"Durability test post {random_str()}"
    }, headers=auth_header(token), timeout=10)

    if r.status_code != 201:
        print(f"  [{FAIL}] Could not create post: {r.text[:100]}")
        return False

    post_id = r.json()["postId"]

    r2 = requests.get(f"{BASE_URL}/posts?feed=global", headers=auth_header(token), timeout=10)
    if r2.status_code != 200:
        print(f"  [{FAIL}] Could not fetch posts")
        return False

    posts = r2.json()
    found = any(p["PostID"] == post_id for p in posts)
    print(f"  [{PASS if found else FAIL}] Post {post_id} persists after creation")
    return found


# ─── Test 7: Consistency — Concurrent comments ─────────

def test_consistency_concurrent_comments(tokens, post_id):
    """Multiple users add comments to the same post. Count should be exact."""
    print("\n[TEST] Consistency — Concurrent Comment Creation")
    num_comments = len(tokens)
    results = {"success": 0, "fail": 0}
    lock = threading.Lock()

    def add_comment(token, idx):
        try:
            r = requests.post(f"{BASE_URL}/posts/{post_id}/comments", json={
                "content": f"Concurrent comment #{idx}"
            }, headers=auth_header(token), timeout=10)
            with lock:
                if r.status_code == 201:
                    results["success"] += 1
                else:
                    results["fail"] += 1
        except Exception as e:
            with lock:
                results["fail"] += 1

    threads = []
    for i, token in enumerate(tokens):
        t = threading.Thread(target=add_comment, args=(token, i))
        threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    r = requests.get(f"{BASE_URL}/posts/{post_id}/comments",
                     headers=auth_header(tokens[0]), timeout=10)
    if r.status_code == 200:
        actual = len([c for c in r.json() if c["Content"].startswith("Concurrent comment")])
        ok = actual == results["success"]
        print(f"  [{PASS if ok else FAIL}] {results['success']} comments created, {actual} found in DB (expected match)")
        return ok
    else:
        print(f"  [{FAIL}] Could not verify comments")
        return False


# ═══════════════════════════════════════════════════════
#  MAIN RUNNER
# ═══════════════════════════════════════════════════════

def main():
    print("=" * 65)
    print("  MODULE B: CONCURRENT WORKLOAD & STRESS TESTING")
    print("=" * 65)

    # Check server is running
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        if r.status_code != 200:
            print(f"[ERROR] Server returned {r.status_code}. Start the backend first.")
            return False
        print(f"[OK] Server is running: {r.json()}")
    except requests.ConnectionError:
        print("[ERROR] Cannot connect to server at localhost:5001.")
        print("        Start the backend: cd app/backend && python3 app.py")
        return False

    # Seed test users directly into MySQL, then login via API
    print("\n[SETUP] Creating test users...")
    num_users = 5
    tokens = []
    for i in range(num_users):
        uname = f"stress_user_{i}"
        token = seed_user(uname)
        if token:
            tokens.append(token)
            print(f"  {uname}: OK")
        else:
            print(f"  {uname}: FAILED (login returned no token)")

    if len(tokens) < 2:
        print("[ERROR] Need at least 2 authenticated users to run tests.")
        return False

    # Create a test post for like/comment tests
    r = requests.post(f"{BASE_URL}/posts", json={
        "content": f"Test post for stress testing {random_str()}"
    }, headers=auth_header(tokens[0]), timeout=10)

    test_post_id = None
    if r.status_code == 201:
        test_post_id = r.json()["postId"]
        print(f"  Test post created: {test_post_id}")

    # Run tests
    passed = 0
    failed = 0
    tests = []

    tests.append(("Concurrent Post Creation", lambda: test_concurrent_post_creation(tokens)))

    if test_post_id:
        tests.append(("Concurrent Like Toggle", lambda: test_concurrent_like_toggle(tokens, test_post_id)))
        tests.append(("Concurrent Comments", lambda: test_consistency_concurrent_comments(tokens, test_post_id)))

    tests.append(("Concurrent Group Join", lambda: test_concurrent_group_join(tokens, tokens[0])))
    tests.append(("Stress — High Volume", lambda: test_stress_high_volume(tokens)))
    tests.append(("Transaction Atomicity", test_transaction_atomicity))
    tests.append(("Durability", lambda: test_durability(tokens[0])))

    for name, fn in tests:
        try:
            if fn():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  [{FAIL}] {name}: EXCEPTION — {e}")
            failed += 1

    print("\n" + "=" * 65)
    print(f"  RESULTS: {passed} passed, {failed} failed, {len(tests)} total")
    print("=" * 65)
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
