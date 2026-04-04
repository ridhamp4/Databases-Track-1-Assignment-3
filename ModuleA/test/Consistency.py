import os

from database.db_manager import DatabaseManager


def log_path():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "consistency.log"))


def setup_db(dbm):
    dbm.create_database("ConsistencyDB")
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
        "ConsistencyDB",
        "Users",
        schema_users,
        order=4,
        search_key="user_id",
        constraints=users_constraints,
    )
    dbm.create_table(
        "ConsistencyDB",
        "Products",
        schema_products,
        order=4,
        search_key="product_id",
        constraints=products_constraints,
    )
    dbm.create_table(
        "ConsistencyDB",
        "Orders",
        schema_orders,
        order=4,
        search_key="order_id",
        constraints=orders_constraints,
    )
    users = dbm.get_table("ConsistencyDB", "Users")
    products = dbm.get_table("ConsistencyDB", "Products")
    orders = dbm.get_table("ConsistencyDB", "Orders")
    return users, products, orders


def seed(users, products):
    if users.get(1) is None:
        users.insert({"user_id": 1, "name": "Ada", "balance": 100})
    if products.get(10) is None:
        products.insert({"product_id": 10, "name": "Widget", "stock": 5, "price": 10})


def main():
    if os.path.exists(log_path()):
        os.remove(log_path())

    dbm = DatabaseManager(log_path=log_path())
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
        "order_id": 200,
        "user_id": 1,
        "product_id": 10,
        "qty": 1,
        "total": 10,
    }

    users.update(1, new_user, tx_id=tx_id)
    products.update(10, new_product, tx_id=tx_id)
    orders.insert(order, tx_id=tx_id)
    dbm.commit(tx_id)

    tx_id = dbm.begin()
    product = products.get(10)
    bad_product = dict(product)
    bad_product["stock"] = -1
    try:
        products.update(10, bad_product, tx_id=tx_id)
        dbm.commit(tx_id)
        print("FAIL: negative stock update was accepted.")
        return 1
    except ValueError as exc:
        print("Expected failure for negative stock:", exc)
        dbm.rollback(tx_id)

    product = products.get(10)
    if product is None or product.get("stock") < 0:
        print("FAIL: negative stock persisted after rollback.")
        return 1

    tx_id = dbm.begin()
    user = users.get(1)
    bad_user = dict(user)
    bad_user["balance"] = -1000
    print("Attempting negative balance update: current=", user.get("balance"), "new=", bad_user["balance"])
    try:
        users.update(1, bad_user, tx_id=tx_id)
        dbm.commit(tx_id)
        print("FAIL: negative balance update was accepted.")
        return 1
    except ValueError as exc:
        print("Expected failure for negative balance:", exc)
        dbm.rollback(tx_id)

    rolled_back_user = users.get(1)
    print("After rollback, balance=", rolled_back_user.get("balance"))
    if rolled_back_user is None or rolled_back_user.get("balance") < 0:
        print("FAIL: negative balance persisted after rollback.")
        return 1

    tx_id = dbm.begin()
    bad_order = {
        "order_id": 201,
        "user_id": 999,
        "product_id": 10,
        "qty": 1,
        "total": 10,
    }
    try:
        orders.insert(bad_order, tx_id=tx_id)
        dbm.commit(tx_id)
        print("FAIL: invalid order reference was accepted.")
        return 1
    except ValueError as exc:
        print("Expected failure for invalid order reference:", exc)
        dbm.rollback(tx_id)

    if orders.get(201) is not None:
        print("FAIL: invalid order persisted after rollback.")
        return 1

    print("PASS: consistency verified by database constraints.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
