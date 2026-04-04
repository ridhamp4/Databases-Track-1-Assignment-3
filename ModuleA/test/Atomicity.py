import argparse
import os
import sys

from database.db_manager import DatabaseManager


def log_path():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "atomicity.log"))


def setup_db(dbm):
    dbm.create_database("AtomicityDB")
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
        "AtomicityDB",
        "Users",
        schema_users,
        order=4,
        search_key="user_id",
        constraints=users_constraints,
    )
    dbm.create_table(
        "AtomicityDB",
        "Products",
        schema_products,
        order=4,
        search_key="product_id",
        constraints=products_constraints,
    )
    dbm.create_table(
        "AtomicityDB",
        "Orders",
        schema_orders,
        order=4,
        search_key="order_id",
        constraints=orders_constraints,
    )
    users = dbm.get_table("AtomicityDB", "Users")
    products = dbm.get_table("AtomicityDB", "Products")
    orders = dbm.get_table("AtomicityDB", "Orders")
    return users, products, orders


def seed(users, products):
    if users.get(1) is None:
        users.insert({"user_id": 1, "name": "Ada", "balance": 100})
    if products.get(10) is None:
        products.insert({"product_id": 10, "name": "Widget", "stock": 5, "price": 10})


def crash_run():
    path = log_path()
    if os.path.exists(path):
        os.remove(path)

    dbm = DatabaseManager(log_path=path)
    users, products, orders = setup_db(dbm)
    seed(users, products)

    tx_id = dbm.begin()
    user = users.get(1)
    product = products.get(10)

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

    print("Simulating crash after multi-table writes (no commit/rollback).")
    sys.exit(2)


def verify():
    dbm = DatabaseManager(log_path=log_path())
    users, products, orders = setup_db(dbm)

    user = users.get(1)
    product = products.get(10)
    order = orders.get(100)

    ok = True
    if user is None or user.get("balance") != 100:
        ok = False
    if product is None or product.get("stock") != 5:
        ok = False
    if order is not None:
        ok = False

    if ok:
        print("PASS: atomicity verified (no partial updates).")
        return 0
    print("FAIL: atomicity violation detected.")
    print("Users:", users.get_all())
    print("Products:", products.get_all())
    print("Orders:", orders.get_all())
    return 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["crash", "verify"], required=True)
    args = parser.parse_args()

    if args.mode == "crash":
        crash_run()
    return verify()


if __name__ == "__main__":
    raise SystemExit(main())
