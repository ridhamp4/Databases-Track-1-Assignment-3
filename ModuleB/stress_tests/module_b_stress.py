#!/usr/bin/env python3
"""Module B multi-user behaviour and stress testing harness for IITGN Connect.

This script exercises the live Flask API with:
- concurrent multi-user usage
- race-condition probes on shared resources
- failure simulation with rollback verification
- read-heavy stress testing

It is intentionally self-contained so it can run without extra Python packages.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from importlib import import_module
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "Assignment2" / "app" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

get_db = import_module("db").get_db


DEFAULT_BASE_URL = os.environ.get("IITGN_CONNECT_BASE_URL", "http://localhost:5001")
DEFAULT_OUTPUT = SCRIPT_DIR / "module_b_results.json"
DEFAULT_TIMEOUT = float(os.environ.get("IITGN_CONNECT_TIMEOUT", "12"))
WRITE_RETRY_ATTEMPTS = int(os.environ.get("IITGN_CONNECT_WRITE_RETRIES", "3"))
WRITE_RETRY_DELAY = float(os.environ.get("IITGN_CONNECT_WRITE_RETRY_DELAY", "0.15"))

DEFAULT_USERS = [
    {"username": "admin_user", "password": "password123"},
    {"username": "laksh_jain", "password": "password123"},
    {"username": "parthiv_p", "password": "password123"},
    {"username": "ridham_p", "password": "password123"},
    {"username": "shriniket_b", "password": "password123"},
    {"username": "rudra_s", "password": "password123"},
    {"username": "prof_yogesh", "password": "password123"},
    {"username": "alumni_rahul", "password": "password123"},
]


@dataclass
class UserSession:
    username: str
    member_id: int
    token: str


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def http_json_request(base_url: str, method: str, path: str, payload=None, token: str | None = None, timeout: float = DEFAULT_TIMEOUT):
    url = base_url.rstrip("/") + path
    headers = {"Accept": "application/json"}
    data = None

    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            elapsed_ms = (time.perf_counter() - started) * 1000
            return {
                "ok": 200 <= response.status < 300,
                "status": response.status,
                "elapsed_ms": elapsed_ms,
                "data": json.loads(body) if body else None,
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        elapsed_ms = (time.perf_counter() - started) * 1000
        try:
            parsed = json.loads(body) if body else None
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return {
            "ok": False,
            "status": exc.code,
            "elapsed_ms": elapsed_ms,
            "data": parsed,
        }
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        return {
            "ok": False,
            "status": None,
            "elapsed_ms": elapsed_ms,
            "error": str(exc),
            "data": None,
        }


def http_json_request_with_retry(base_url: str, method: str, path: str, payload=None, token: str | None = None, timeout: float = DEFAULT_TIMEOUT, retries: int = WRITE_RETRY_ATTEMPTS):
    last_result = None
    for attempt in range(retries + 1):
        result = http_json_request(base_url, method, path, payload=payload, token=token, timeout=timeout)
        last_result = result
        if result.get("ok"):
            return result
        if result.get("status") not in (500, None) or attempt == retries:
            return result
        time.sleep(WRITE_RETRY_DELAY * (attempt + 1))
    return last_result


def db_fetch_all(sql: str, args=()):
    conn = get_db()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, args)
        return cursor.fetchall()
    finally:
        try:
            conn.close()
        except Exception:
            pass


def db_fetch_one(sql: str, args=()):
    rows = db_fetch_all(sql, args)
    return rows[0] if rows else None


def login_users(base_url: str, users):
    sessions = []
    for user in users:
        result = http_json_request(
            base_url,
            "POST",
            "/api/auth/login",
            payload={"username": user["username"], "password": user["password"]},
        )
        if not result["ok"]:
            raise RuntimeError(f"Login failed for {user['username']}: {result}")
        body = result["data"] or {}
        sessions.append(
            UserSession(
                username=user["username"],
                member_id=int(body["user"]["MemberID"]),
                token=body["token"],
            )
        )
    return sessions


def create_post_artifact(base_url: str, creator: UserSession, content_prefix: str):
    unique = now_stamp()
    response = http_json_request(
        base_url,
        "POST",
        "/api/posts",
        token=creator.token,
        payload={"content": f"{content_prefix}::{unique}", "groupId": None, "imageUrl": None},
    )
    if not response["ok"]:
        raise RuntimeError(f"Failed to create post artifact: {response}")
    return {"post_id": int(response["data"]["postId"]), "unique": unique}


def create_poll_artifact(base_url: str, creator: UserSession, question_prefix: str):
    unique = now_stamp()
    future_expiry = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat().replace("+00:00", "Z")
    response = http_json_request(
        base_url,
        "POST",
        "/api/polls/",
        token=creator.token,
        payload={
            "question": f"{question_prefix}::{unique}",
            "expiresAt": future_expiry,
            "options": ["Option A", "Option B"],
        },
    )
    if not response["ok"]:
        raise RuntimeError(f"Failed to create poll artifact: {response}")

    poll_id = int(response["data"]["pollId"])
    poll_options = db_fetch_all(
        "SELECT OptionID, OptionText FROM PollOption WHERE PollID = %s ORDER BY OptionID",
        (poll_id,),
    )
    if len(poll_options) < 2:
        raise RuntimeError("Poll options were not created correctly")

    return {
        "poll_id": poll_id,
        "poll_option_id": int(poll_options[0]["OptionID"]),
        "unique": unique,
    }


def create_group_artifact(base_url: str, creator: UserSession, group_prefix: str):
    unique = now_stamp()
    response = http_json_request(
        base_url,
        "POST",
        "/api/groups/",
        token=creator.token,
        payload={
            "name": f"{group_prefix}_{unique}",
            "description": "Temporary group for Module B stress testing",
            "isRestricted": False,
        },
    )
    if not response["ok"]:
        raise RuntimeError(f"Failed to create group artifact: {response}")
    return {"group_id": int(response["data"]["groupId"]), "unique": unique}


def summarize_requests(results):
    summary = {"ok": 0, "fail": 0, "status_counts": {}}
    for result in results:
        if result.get("ok"):
            summary["ok"] += 1
        else:
            summary["fail"] += 1
        status_key = str(result.get("status"))
        summary["status_counts"][status_key] = summary["status_counts"].get(status_key, 0) + 1
    return summary


def run_concurrent_usage(base_url: str, sessions, shared, ops_per_activity: int, concurrency: int):
    participants = sessions[1:7] or sessions[:1]
    participant_ids = [session.member_id for session in participants]
    unique_participant_ids = set(participant_ids)

    like_calls_by_member = {member_id: 0 for member_id in unique_participant_ids}
    vote_calls_by_member = {member_id: 0 for member_id in unique_participant_ids}
    join_calls_by_member = {member_id: 0 for member_id in unique_participant_ids}

    like_inputs = []
    comment_inputs = []
    vote_inputs = []
    join_inputs = []
    for index in range(ops_per_activity):
        session = participants[index % len(participants)]
        like_calls_by_member[session.member_id] += 1
        vote_calls_by_member[session.member_id] += 1
        join_calls_by_member[session.member_id] += 1
        like_inputs.append(session)
        comment_inputs.append((session, index))
        vote_inputs.append(session)
        join_inputs.append(session)

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        like_results = list(
            executor.map(
                lambda session: http_json_request_with_retry(
                    base_url,
                    "POST",
                    f"/api/posts/{shared['post_id']}/like",
                    None,
                    session.token,
                ),
                like_inputs,
            )
        )

    like_successes_by_member = {member_id: 0 for member_id in unique_participant_ids}
    for session, result in zip(like_inputs, like_results):
        if result.get("ok"):
            like_successes_by_member[session.member_id] += 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        comment_results = list(
            executor.map(
                lambda item: http_json_request_with_retry(
                    base_url,
                    "POST",
                    f"/api/posts/{shared['post_id']}/comments",
                    {"content": f"Concurrent comment #{item[1]} from {item[0].username}"},
                    item[0].token,
                ),
                comment_inputs,
            )
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        vote_results = list(
            executor.map(
                lambda session: http_json_request_with_retry(
                    base_url,
                    "POST",
                    f"/api/polls/{shared['poll_id']}/vote",
                    {"optionId": shared["poll_option_id"]},
                    session.token,
                ),
                vote_inputs,
            )
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        join_results = list(
            executor.map(
                lambda session: http_json_request_with_retry(
                    base_url,
                    "POST",
                    f"/api/groups/{shared['group_id']}/join",
                    None,
                    session.token,
                ),
                join_inputs,
            )
        )

    expected_votes = sum(1 for count in vote_calls_by_member.values() if count > 0)
    expected_group_members = sum(1 for count in join_calls_by_member.values() if count > 0) + 1

    db_counts = {
        "likes": db_fetch_one("SELECT COUNT(*) AS c FROM PostLike WHERE PostID = %s", (shared["post_id"],))["c"],
        "comments": db_fetch_one("SELECT COUNT(*) AS c FROM Comment WHERE PostID = %s", (shared["post_id"],))["c"],
        "votes": db_fetch_one(
            "SELECT COUNT(*) AS c FROM PollVote pv JOIN PollOption po ON pv.OptionID = po.OptionID WHERE po.PollID = %s",
            (shared["poll_id"],),
        )["c"],
        "group_members": db_fetch_one(
            "SELECT COUNT(*) AS c FROM GroupMembership WHERE GroupID = %s AND Status = 'approved'",
            (shared["group_id"],),
        )["c"],
    }

    return {
        "name": "concurrent_usage",
        "participants": [session.username for session in participants],
        "requests": {
            "likes": summarize_requests(like_results),
            "comments": summarize_requests(comment_results),
            "votes": summarize_requests(vote_results),
            "joins": summarize_requests(join_results),
        },
        "db_counts": db_counts,
        "expected": {
            "likesMin": 0,
            "likesMax": len(unique_participant_ids),
            "comments": ops_per_activity,
            "votes": expected_votes,
            "group_members": expected_group_members,
        },
        "operationsPerActivity": ops_per_activity,
        "concurrency": concurrency,
    }


def run_race_probes_for_artifacts(base_url: str, sessions, shared_post_id: int, race_poll: dict, race_group: dict, attempts: int, concurrency: int):
    actor = sessions[2] if len(sessions) > 2 else sessions[0]

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        vote_futures = [executor.submit(http_json_request_with_retry, base_url, "POST", f"/api/polls/{race_poll['poll_id']}/vote", {"optionId": race_poll["poll_option_id"]}, actor.token) for _ in range(attempts)]
        join_futures = [executor.submit(http_json_request_with_retry, base_url, "POST", f"/api/groups/{race_group['group_id']}/join", None, actor.token) for _ in range(attempts)]
        like_futures = [executor.submit(http_json_request_with_retry, base_url, "POST", f"/api/posts/{shared_post_id}/like", None, actor.token) for _ in range(attempts)]

        vote_results = [future.result() for future in vote_futures]
        join_results = [future.result() for future in join_futures]
        like_results = [future.result() for future in like_futures]

    return {
        "name": "race_condition_probes",
        "actor": actor.username,
        "requests": {
            "votes": summarize_requests(vote_results),
            "joins": summarize_requests(join_results),
            "likes": summarize_requests(like_results),
        },
        "db_checks": {
            "post_like_rows_for_actor": db_fetch_one(
                "SELECT COUNT(*) AS c FROM PostLike WHERE PostID = %s AND MemberID = %s",
                (shared_post_id, actor.member_id),
            )["c"],
            "poll_vote_rows_for_actor": db_fetch_one(
                "SELECT COUNT(*) AS c FROM PollVote pv JOIN PollOption po ON pv.OptionID = po.OptionID WHERE po.PollID = %s AND pv.MemberID = %s",
                (race_poll["poll_id"], actor.member_id),
            )["c"],
            "group_membership_rows_for_actor": db_fetch_one(
                "SELECT COUNT(*) AS c FROM GroupMembership WHERE GroupID = %s AND MemberID = %s",
                (race_group["group_id"], actor.member_id),
            )["c"],
        },
        "artifacts": {
            "race_poll_id": race_poll["poll_id"],
            "race_group_id": race_group["group_id"],
        },
        "attempts": attempts,
        "concurrency": concurrency,
        "expected": {
            "post_like_rows_for_actor_min": 0,
            "post_like_rows_for_actor_max": 1,
            "poll_vote_rows_for_actor": 1,
            "group_membership_rows_for_actor": 1,
        },
    }


def run_failure_simulation(creator: UserSession, iterations: int):
    conn = get_db()
    marker_prefix = f"MODULE_B_ROLLBACK::{now_stamp()}"
    forced_errors_seen = 0
    unexpected_successes = 0
    last_error_message = None

    try:
        for index in range(iterations):
            marker = f"{marker_prefix}::{index}"
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO Post (AuthorID, GroupID, Content, ImageURL, CreatedAt) VALUES (%s,%s,%s,%s,NOW())",
                    (creator.member_id, None, marker, None),
                )
                cursor.execute("INSERT INTO DefinitelyMissingTable (x) VALUES (1)")
                conn.commit()
                unexpected_successes += 1
            except Exception as exc:
                last_error_message = str(exc)
                forced_errors_seen += 1
                try:
                    conn.rollback()
                except Exception:
                    pass
            finally:
                cursor.close()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    remaining = db_fetch_one("SELECT COUNT(*) AS c FROM Post WHERE Content LIKE %s", (f"{marker_prefix}%",))

    return {
        "name": "failure_simulation",
        "iterations": iterations,
        "forced_errors_seen": forced_errors_seen,
        "unexpected_successes": unexpected_successes,
        "success": unexpected_successes == 0,
        "error_message": last_error_message,
        "rolled_back_row_count": remaining["c"],
    }


def run_stress_test(base_url: str, sessions, request_count: int, concurrency: int):
    endpoints = [
        ("GET", "/api/posts", None),
        ("GET", "/api/groups/", None),
        ("GET", "/api/polls/", None),
    ]

    timings = []
    statuses = {}

    def worker(index: int):
        session = sessions[index % len(sessions)]
        method, path, payload = endpoints[index % len(endpoints)]
        return http_json_request(base_url, method, path, payload, session.token)

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        for result in executor.map(worker, range(request_count)):
            timings.append(result["elapsed_ms"])
            status_key = str(result.get("status"))
            statuses[status_key] = statuses.get(status_key, 0) + 1

    p50 = statistics.median(timings) if timings else 0.0
    p95 = statistics.quantiles(timings, n=20)[18] if len(timings) >= 20 else max(timings, default=0.0)
    return {
        "name": "stress_test",
        "requests": request_count,
        "concurrency": concurrency,
        "timings_ms": {
            "min": min(timings) if timings else 0.0,
            "p50": p50,
            "p95": p95,
            "max": max(timings) if timings else 0.0,
            "average": statistics.fmean(timings) if timings else 0.0,
        },
        "status_counts": statuses,
    }


def cleanup_artifacts(base_url: str, creator: UserSession, shared: dict, race_probes: dict):
    http_json_request(base_url, "DELETE", f"/api/polls/{race_probes['artifacts']['race_poll_id']}", token=creator.token)
    http_json_request(base_url, "DELETE", f"/api/groups/{race_probes['artifacts']['race_group_id']}", token=creator.token)
    http_json_request(base_url, "DELETE", f"/api/polls/{shared['poll_id']}", token=creator.token)
    http_json_request(base_url, "DELETE", f"/api/groups/{shared['group_id']}", token=creator.token)
    http_json_request(base_url, "DELETE", f"/api/posts/{shared['post_id']}", token=creator.token)


def aggregate_verdict(concurrent_usage, race_probes, failure_simulation, stress_test):
    concurrent_ok = (
        concurrent_usage["expected"]["likesMin"] <= concurrent_usage["db_counts"]["likes"] <= concurrent_usage["expected"]["likesMax"]
        and concurrent_usage["db_counts"]["comments"] == concurrent_usage["expected"]["comments"]
        and concurrent_usage["db_counts"]["votes"] == concurrent_usage["expected"]["votes"]
        and concurrent_usage["db_counts"]["group_members"] == concurrent_usage["expected"]["group_members"]
    )
    race_ok = (
        race_probes["expected"]["post_like_rows_for_actor_min"] <= race_probes["db_checks"]["post_like_rows_for_actor"] <= race_probes["expected"]["post_like_rows_for_actor_max"]
        and race_probes["db_checks"]["poll_vote_rows_for_actor"] == race_probes["expected"]["poll_vote_rows_for_actor"]
        and race_probes["db_checks"]["group_membership_rows_for_actor"] == race_probes["expected"]["group_membership_rows_for_actor"]
    )
    rollback_ok = (
        failure_simulation["rolled_back_row_count"] == 0
        and failure_simulation["forced_errors_seen"] == failure_simulation["iterations"]
        and failure_simulation["unexpected_successes"] == 0
    )
    stress_ok = set(stress_test["status_counts"].keys()) == {"200"}
    return {
        "concurrent_usage_ok": concurrent_ok,
        "race_conditions_ok": race_ok,
        "rollback_ok": rollback_ok,
        "stress_ok": stress_ok,
        "overall_ok": concurrent_ok and race_ok and rollback_ok and stress_ok,
    }


def print_assignment_summary(concurrent_usage, race_probes, failure_simulation, stress_test, verdict):
    section1_ok = verdict["concurrent_usage_ok"]
    section2_ok = verdict["race_conditions_ok"]
    section3_ok = verdict["rollback_ok"]
    section4_ok = verdict["stress_ok"]

    print("\nAssignment 3 Module B Summary")
    print("1. Concurrent Usage")
    print(
        f"   Status: {'PASS' if section1_ok else 'FAIL'} | "
        f"likes={concurrent_usage['db_counts']['likes']}/{concurrent_usage['expected']['likesMin']}..{concurrent_usage['expected']['likesMax']}, "
        f"comments={concurrent_usage['db_counts']['comments']}/{concurrent_usage['expected']['comments']}, "
        f"votes={concurrent_usage['db_counts']['votes']}/{concurrent_usage['expected']['votes']}, "
        f"group_members={concurrent_usage['db_counts']['group_members']}/{concurrent_usage['expected']['group_members']}"
    )

    print("2. Race Condition Testing")
    print(
        f"   Status: {'PASS' if section2_ok else 'FAIL'} | "
        f"post_like_rows={race_probes['db_checks']['post_like_rows_for_actor']}, "
        f"poll_vote_rows={race_probes['db_checks']['poll_vote_rows_for_actor']}, "
        f"group_membership_rows={race_probes['db_checks']['group_membership_rows_for_actor']}"
    )

    print("3. Failure Simulation")
    print(
        f"   Status: {'PASS' if section3_ok else 'FAIL'} | "
        f"rolled_back_row_count={failure_simulation['rolled_back_row_count']}, "
        f"forced_errors_seen={failure_simulation['forced_errors_seen']}/{failure_simulation['iterations']}, "
        f"unexpected_successes={failure_simulation['unexpected_successes']}"
    )

    print("4. Stress Testing")
    print(
        f"   Status: {'PASS' if section4_ok else 'FAIL'} | "
        f"requests={stress_test['requests']}, concurrency={stress_test['concurrency']}, "
        f"p50={stress_test['timings_ms']['p50']:.2f}ms, p95={stress_test['timings_ms']['p95']:.2f}ms"
    )

    print(f"Overall: {'PASS' if verdict['overall_ok'] else 'FAIL'}")


def main():
    parser = argparse.ArgumentParser(description="Run Module B multi-user behavior and stress tests.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Backend base URL, e.g. http://localhost:5001")
    parser.add_argument("--users", type=int, default=1000, help="Number of seeded users to log in and use")
    parser.add_argument("--concurrent-ops", type=int, default=1000, help="Operations per activity in concurrent usage")
    parser.add_argument("--concurrent-concurrency", type=int, default=128, help="Worker count for concurrent-usage activity batches")
    parser.add_argument("--race-attempts", type=int, default=1000, help="Attempts per operation in race-condition probes")
    parser.add_argument("--race-concurrency", type=int, default=128, help="Worker count for race-condition probes")
    parser.add_argument("--failure-iterations", type=int, default=1000, help="Number of forced-failure transaction iterations")
    parser.add_argument("--stress-requests", type=int, default=1000, help="Total number of stress-test requests")
    parser.add_argument("--stress-concurrency", type=int, default=64, help="Concurrent workers for the stress phase")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Where to write the JSON summary")
    parser.add_argument("--no-cleanup", action="store_true", help="Keep temporary posts, polls, and groups")
    args = parser.parse_args()

    session_count = max(2, args.users)
    selected_users = [DEFAULT_USERS[i % len(DEFAULT_USERS)] for i in range(session_count)]
    print(
        f"Logging in {len(selected_users)} user sessions against {args.base_url} "
        f"(cycled from {len(DEFAULT_USERS)} seed accounts) ..."
    )
    sessions = login_users(args.base_url, selected_users)

    shared_post = create_post_artifact(args.base_url, sessions[0], "MODULE_B_SHARED_POST")
    shared_poll = create_poll_artifact(args.base_url, sessions[0], "MODULE_B_SHARED_POLL")
    shared_group = create_group_artifact(args.base_url, sessions[0], "MODULE_B_SHARED_GROUP")

    shared = {
        "post_id": shared_post["post_id"],
        "poll_id": shared_poll["poll_id"],
        "poll_option_id": shared_poll["poll_option_id"],
        "group_id": shared_group["group_id"],
    }

    concurrent_usage = run_concurrent_usage(
        args.base_url,
        sessions,
        shared,
        ops_per_activity=args.concurrent_ops,
        concurrency=args.concurrent_concurrency,
    )
    race_poll = create_poll_artifact(args.base_url, sessions[0], "MODULE_B_RACE_POLL")
    race_group = create_group_artifact(args.base_url, sessions[0], "MODULE_B_RACE_GROUP")
    race_probes = run_race_probes_for_artifacts(
        args.base_url,
        sessions,
        shared["post_id"],
        race_poll,
        race_group,
        attempts=args.race_attempts,
        concurrency=args.race_concurrency,
    )
    failure_simulation = run_failure_simulation(sessions[0], iterations=args.failure_iterations)
    stress_test = run_stress_test(args.base_url, sessions, args.stress_requests, args.stress_concurrency)
    verdict = aggregate_verdict(concurrent_usage, race_probes, failure_simulation, stress_test)

    if not args.no_cleanup:
        cleanup_artifacts(args.base_url, sessions[0], shared, race_probes)

    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "baseUrl": args.base_url,
        "users": [session.username for session in sessions],
        "sharedArtifacts": shared,
        "concurrentUsage": concurrent_usage,
        "raceConditionProbes": race_probes,
        "failureSimulation": failure_simulation,
        "stressTest": stress_test,
        "verdict": verdict,
    }

    output_path = Path(args.output)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print_assignment_summary(concurrent_usage, race_probes, failure_simulation, stress_test, verdict)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    print(f"Detailed results written to {output_path}")
    if not verdict["overall_ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
