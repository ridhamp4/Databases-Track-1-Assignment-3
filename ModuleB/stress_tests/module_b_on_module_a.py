#!/usr/bin/env python3
"""Module B implementation over Module A transaction engine.

This script stress-tests the Module A B+Tree database engine using:
- concurrent multi-relation transactions
- race-condition probing on shared stock
- failure injection + rollback checks
- restart durability verification

Outputs a JSON report suitable for Assignment 3 submission evidence.
"""

from __future__ import annotations

import argparse
import importlib
import json
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
MODULE_A_DIR = PROJECT_ROOT / "ModuleA"

if str(MODULE_A_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_A_DIR))

DatabaseManager = importlib.import_module("database.db_manager").DatabaseManager
DatabaseManagerType = Any


class OrderIdGenerator:
    def __init__(self, start: int = 1):
        self._next = start
        self._lock = threading.Lock()

    def next_id(self) -> int:
        with self._lock:
            value = self._next
            self._next += 1
            return value


def build_db_manager(log_path: Path) -> DatabaseManagerType:
    return DatabaseManager(log_path=str(log_path))


def reset_log_file(log_path: Path) -> None:
    if log_path.exists():
        log_path.unlink()


def create_schema(dbm: DatabaseManagerType, db_name: str) -> None:
    dbm.create_database(db_name)

    users_schema = {
        "user_id": "int",
        "name": "str",
        "balance": "int",
        "city": "str",
    }
    products_schema = {
        "product_id": "int",
        "name": "str",
        "stock": "int",
        "price": "int",
    }
    orders_schema = {
        "order_id": "int",
        "user_id": "int",
        "product_id": "int",
        "amount": "int",
        "status": "str",
        "ts": "int",
    }

    users_constraints = {
        "non_negative": ["balance"],
    }
    products_constraints = {
        "non_negative": ["stock", "price"],
    }
    orders_constraints = {
        "non_negative": ["amount"],
        "references": {
            "user_id": {"table": "Users", "key": "user_id"},
            "product_id": {"table": "Products", "key": "product_id"},
        },
    }

    dbm.create_table(db_name, "Users", users_schema, order=8, search_key="user_id", constraints=users_constraints)
    dbm.create_table(
        db_name,
        "Products",
        products_schema,
        order=8,
        search_key="product_id",
        constraints=products_constraints,
    )
    dbm.create_table(
        db_name,
        "Orders",
        orders_schema,
        order=8,
        search_key="order_id",
        constraints=orders_constraints,
    )


def get_tables(dbm: DatabaseManagerType, db_name: str):
    return (
        dbm.get_table(db_name, "Users"),
        dbm.get_table(db_name, "Products"),
        dbm.get_table(db_name, "Orders"),
    )


def seed_data(
    dbm: DatabaseManagerType,
    db_name: str,
    user_count: int,
    product_count: int,
    initial_balance: int,
    initial_stock: int,
    unit_price: int,
) -> None:
    users, products, _ = get_tables(dbm, db_name)

    for uid in range(1, user_count + 1):
        users.insert(
            {
                "user_id": uid,
                "name": f"user_{uid}",
                "balance": initial_balance,
                "city": "Gandhinagar",
            }
        )

    for pid in range(1, product_count + 1):
        products.insert(
            {
                "product_id": pid,
                "name": f"product_{pid}",
                "stock": initial_stock,
                "price": unit_price,
            }
        )


def place_order_tx(
    dbm: DatabaseManagerType,
    db_name: str,
    order_ids: OrderIdGenerator,
    user_id: int,
    product_id: int,
    inject_failure: str | None = None,
):
    users, products, orders = get_tables(dbm, db_name)
    tx_id = dbm.begin()

    try:
        user = users.get(user_id)
        product = products.get(product_id)

        if user is None or product is None:
            raise ValueError("Missing reference row")
        if product["stock"] <= 0:
            raise ValueError("Out of stock")
        if user["balance"] < product["price"]:
            raise ValueError("Insufficient balance")

        users.update(
            user_id,
            {
                "user_id": user_id,
                "name": user["name"],
                "balance": user["balance"] - product["price"],
                "city": user.get("city", ""),
            },
            tx_id=tx_id,
        )

        if inject_failure == "after_user":
            raise RuntimeError("Injected failure after users update")

        products.update(
            product_id,
            {
                "product_id": product_id,
                "name": product["name"],
                "stock": product["stock"] - 1,
                "price": product["price"],
            },
            tx_id=tx_id,
        )

        if inject_failure == "after_product":
            raise RuntimeError("Injected failure after products update")

        order_id = order_ids.next_id()
        orders.insert(
            {
                "order_id": order_id,
                "user_id": user_id,
                "product_id": product_id,
                "amount": product["price"],
                "status": "PLACED",
                "ts": int(time.time() * 1000),
            },
            tx_id=tx_id,
        )

        if inject_failure == "after_order":
            raise RuntimeError("Injected failure after orders insert")

        dbm.commit(tx_id)
        return True, "committed"
    except Exception as exc:
        try:
            dbm.rollback(tx_id)
        except ValueError:
            pass
        return False, str(exc)


def snapshot(dbm: DatabaseManagerType, db_name: str):
    users, products, orders = get_tables(dbm, db_name)
    users_map = {row["user_id"]: row for row in users.get_all()}
    products_map = {row["product_id"]: row for row in products.get_all()}
    orders_map = {row["order_id"]: row for row in orders.get_all()}
    return {"users": users_map, "products": products_map, "orders": orders_map}


def validate_consistency(state, initial_balance_total: int, initial_stock_total: int):
    users = state["users"].values()
    products = state["products"].values()
    orders = state["orders"].values()

    if any(u["balance"] < 0 for u in users):
        return False, "Negative user balance found"
    if any(p["stock"] < 0 for p in products):
        return False, "Negative product stock found"

    spent = sum(o["amount"] for o in orders)
    balance_drop = initial_balance_total - sum(u["balance"] for u in users)
    if spent != balance_drop:
        return False, "Order amount sum and user balance delta mismatch"

    stock_drop = initial_stock_total - sum(p["stock"] for p in products)
    if stock_drop != len(state["orders"]):
        return False, "Order count and stock delta mismatch"

    return True, "Consistency checks passed"


def run_atomicity_case(dbm: DatabaseManagerType, db_name: str, order_ids: OrderIdGenerator):
    before = snapshot(dbm, db_name)
    ok, reason = place_order_tx(
        dbm,
        db_name,
        order_ids,
        user_id=1,
        product_id=1,
        inject_failure="after_product",
    )
    after = snapshot(dbm, db_name)
    return {
        "tx_success": ok,
        "reason": reason,
        "state_unchanged": before == after,
    }


def run_concurrent_load(
    dbm: DatabaseManagerType,
    db_name: str,
    order_ids: OrderIdGenerator,
    workers: int,
    tx_per_worker: int,
    fail_probability: float,
    user_count: int,
    product_count: int,
):
    stats = {
        "attempted": 0,
        "committed": 0,
        "rolled_back": 0,
        "rollback_reasons": {},
    }
    lock = threading.Lock()
    start = time.perf_counter()

    def worker_fn():
        local_attempted = 0
        local_committed = 0
        local_rolled_back = 0
        local_reasons = {}

        for _ in range(tx_per_worker):
            local_attempted += 1
            failure_point = None
            if random.random() < fail_probability:
                failure_point = random.choice(["after_user", "after_product", "after_order"])

            user_id = random.randint(1, user_count)
            product_id = random.randint(1, product_count)
            ok, reason = place_order_tx(
                dbm,
                db_name,
                order_ids,
                user_id=user_id,
                product_id=product_id,
                inject_failure=failure_point,
            )
            if ok:
                local_committed += 1
            else:
                local_rolled_back += 1
                local_reasons[reason] = local_reasons.get(reason, 0) + 1

        return local_attempted, local_committed, local_rolled_back, local_reasons

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker_fn) for _ in range(workers)]
        for future in as_completed(futures):
            attempted, committed, rolled_back, reasons = future.result()
            with lock:
                stats["attempted"] += attempted
                stats["committed"] += committed
                stats["rolled_back"] += rolled_back
                for reason, count in reasons.items():
                    stats["rollback_reasons"][reason] = stats["rollback_reasons"].get(reason, 0) + count

    elapsed = time.perf_counter() - start
    stats["elapsed_sec"] = round(elapsed, 4)
    stats["throughput_tps"] = round(stats["attempted"] / elapsed, 2) if elapsed > 0 else 0
    return stats


def run_race_case(
    dbm: DatabaseManagerType,
    db_name: str,
    order_ids: OrderIdGenerator,
    workers: int,
    attempts: int,
    race_stock: int,
):
    users, products, _ = get_tables(dbm, db_name)

    race_user_id = 9999
    race_product_id = 999

    if users.get(race_user_id) is None:
        users.insert(
            {
                "user_id": race_user_id,
                "name": "race_user",
                "balance": 10**9,
                "city": "Gandhinagar",
            }
        )

    if products.get(race_product_id) is None:
        products.insert(
            {
                "product_id": race_product_id,
                "name": "race_product",
                "stock": race_stock,
                "price": 100,
            }
        )
    else:
        current = products.get(race_product_id)
        products.update(
            race_product_id,
            {
                "product_id": race_product_id,
                "name": current["name"],
                "stock": race_stock,
                "price": current["price"],
            },
        )

    committed = 0
    rolled_back = 0

    def one_attempt():
        return place_order_tx(
            dbm,
            db_name,
            order_ids,
            user_id=race_user_id,
            product_id=race_product_id,
            inject_failure=None,
        )[0]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one_attempt) for _ in range(attempts)]
        for future in as_completed(futures):
            if future.result():
                committed += 1
            else:
                rolled_back += 1

    final_stock = products.get(race_product_id)["stock"]
    valid = committed <= race_stock and final_stock >= 0 and (race_stock - final_stock) == committed
    return {
        "attempted": attempts,
        "committed": committed,
        "rolled_back": rolled_back,
        "initial_stock": race_stock,
        "final_stock": final_stock,
        "valid": valid,
    }


def run_durability_case(log_path: Path, db_name: str, before_state):
    def summarize(state):
        users = state["users"].values()
        products = state["products"].values()
        orders = state["orders"].values()
        return {
            "user_count": len(state["users"]),
            "product_count": len(state["products"]),
            "order_count": len(state["orders"]),
            "sum_balances": sum(u["balance"] for u in users),
            "sum_stock": sum(p["stock"] for p in products),
            "sum_order_amount": sum(o["amount"] for o in orders),
            "max_order_id": max(state["orders"].keys()) if state["orders"] else 0,
        }

    restarted = build_db_manager(log_path)
    create_schema(restarted, db_name)
    after_state = snapshot(restarted, db_name)

    before_summary = summarize(before_state)
    after_summary = summarize(after_state)

    return {
        "ok": before_summary == after_summary,
        "before": before_summary,
        "after": after_summary,
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Module B implementation over Module A")
    parser.add_argument("--db-name", default="A3_ModuleBOverA")
    parser.add_argument("--users", type=int, default=30)
    parser.add_argument("--products", type=int, default=6)
    parser.add_argument("--initial-balance", type=int, default=20000)
    parser.add_argument("--initial-stock", type=int, default=600)
    parser.add_argument("--price", type=int, default=100)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--tx-per-worker", type=int, default=80)
    parser.add_argument("--fail-probability", type=float, default=0.2)
    parser.add_argument("--race-attempts", type=int, default=220)
    parser.add_argument("--race-stock", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--log-file", default="module_b_on_module_a.log")
    parser.add_argument("--report-file", default="module_b_on_module_a_results.json")
    parser.add_argument("--keep-log", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    random.seed(args.seed)

    log_path = SCRIPT_DIR / args.log_file
    report_path = SCRIPT_DIR / args.report_file

    if not args.keep_log:
        reset_log_file(log_path)

    dbm = build_db_manager(log_path)
    create_schema(dbm, args.db_name)
    seed_data(
        dbm,
        args.db_name,
        user_count=args.users,
        product_count=args.products,
        initial_balance=args.initial_balance,
        initial_stock=args.initial_stock,
        unit_price=args.price,
    )

    initial_balance_total = args.users * args.initial_balance
    initial_stock_total = args.products * args.initial_stock

    order_ids = OrderIdGenerator(start=1)

    atomicity = run_atomicity_case(dbm, args.db_name, order_ids)
    concurrent = run_concurrent_load(
        dbm,
        args.db_name,
        order_ids,
        workers=args.workers,
        tx_per_worker=args.tx_per_worker,
        fail_probability=args.fail_probability,
        user_count=args.users,
        product_count=args.products,
    )
    consistency_state = snapshot(dbm, args.db_name)
    consistency_ok, consistency_msg = validate_consistency(
        consistency_state,
        initial_balance_total,
        initial_stock_total,
    )

    race = run_race_case(
        dbm,
        args.db_name,
        order_ids,
        workers=args.workers,
        attempts=args.race_attempts,
        race_stock=args.race_stock,
    )

    pre_restart_state = snapshot(dbm, args.db_name)
    durability = run_durability_case(log_path, args.db_name, pre_restart_state)

    report = {
        "config": vars(args),
        "atomicity_failure": atomicity,
        "concurrent_workload": concurrent,
        "consistency": {"ok": consistency_ok, "message": consistency_msg},
        "race_condition": race,
        "durability": durability,
        "acid_summary": {
            "atomicity": bool(atomicity["state_unchanged"]),
            "consistency": bool(consistency_ok),
            "isolation": bool(race["valid"]),
            "durability": bool(durability["ok"]),
        },
    }

    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=== Module B over Module A Report ===")
    print(json.dumps(report, indent=2))
    print(f"\nReport written to: {report_path}")


if __name__ == "__main__":
    main()
