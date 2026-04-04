import argparse
import os
import sys

from database.db_manager import DatabaseManager


def log_path():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "multi_relation.log"))


def ensure_base_data(users, products, orders):
    if users.get(1) is None:
        users.insert({"user_id": 1, "name": "Ada", "balance": 100})
    if products.get(10) is None:
        products.insert({"product_id": 10, "name": "Widget", "stock": 5, "price": 10})
    if orders.get(100) is not None:
        orders.delete(100)


def run_transaction(dbm, users, products, orders, mode):
    tx_id = dbm.begin()

    user = users.get(1)
    product = products.get(10)

    if user is None or product is None:
        raise RuntimeError("Base records missing; run setup first.")

    new_user = dict(user)
    new_user["balance"] = user["balance"] - 10

    new_product = dict(product)
    new_product["stock"] = product["stock"] - 1

    order = {
        "order_id": 100,
        "user_id": 1,
        "product_id": 10,
        "qty": 1,
        "total": 10,
    }

    users.update(1, new_user, tx_id=tx_id)
    products.update(10, new_product, tx_id=tx_id)
    orders.insert(order, tx_id=tx_id)

    if mode == "commit":
        dbm.commit(tx_id)
        return
    if mode == "rollback":
        dbm.rollback(tx_id)
        return
    if mode == "crash":
        print("Simulating crash after writes (no commit/rollback)")
        sys.exit(2)


def print_state(users, products, orders):
    print("Users:", users.get_all())
    print("Products:", products.get_all())
    print("Orders:", orders.get_all())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["commit", "rollback", "crash", "verify"],
        default="commit",
    )
    args = parser.parse_args()

    if args.mode in {"commit", "rollback", "crash"}:
        if os.path.exists(log_path()):
            os.remove(log_path())

    dbm = DatabaseManager(log_path=log_path())
    dbm.create_database("ShopDB")

    schema_users = {"user_id": "int", "name": "str", "balance": "int"}
    schema_products = {"product_id": "int", "name": "str", "stock": "int", "price": "int"}
    schema_orders = {
        "order_id": "int",
        "user_id": "int",
        "product_id": "int",
        "qty": "int",
        "total": "int",
    }

    users_constraints = {"non_negative": ["balance"]}
    products_constraints = {"non_negative": ["stock", "price"]}
    orders_constraints = {
        "non_negative": ["qty", "total"],
        "references": {
            "user_id": {"table": "Users", "key": "user_id"},
            "product_id": {"table": "Products", "key": "product_id"},
        },
    }

    dbm.create_table(
        "ShopDB",
        "Users",
        schema_users,
        order=4,
        search_key="user_id",
        constraints=users_constraints,
    )
    dbm.create_table(
        "ShopDB",
        "Products",
        schema_products,
        order=4,
        search_key="product_id",
        constraints=products_constraints,
    )
    dbm.create_table(
        "ShopDB",
        "Orders",
        schema_orders,
        order=4,
        search_key="order_id",
        constraints=orders_constraints,
    )

    users = dbm.get_table("ShopDB", "Users")
    products = dbm.get_table("ShopDB", "Products")
    orders = dbm.get_table("ShopDB", "Orders")

    ensure_base_data(users, products, orders)

    if args.mode == "verify":
        print_state(users, products, orders)
        return

    run_transaction(dbm, users, products, orders, args.mode)
    print_state(users, products, orders)


if __name__ == "__main__":
    main()
