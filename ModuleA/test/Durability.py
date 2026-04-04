import os

from database.db_manager import DatabaseManager


def log_path():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "durability.log"))


def setup_db(dbm):
    dbm.create_database("DurabilityDB")
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
        "DurabilityDB",
        "Users",
        schema_users,
        order=4,
        search_key="user_id",
        constraints=users_constraints,
    )
    dbm.create_table(
        "DurabilityDB",
        "Products",
        schema_products,
        order=4,
        search_key="product_id",
        constraints=products_constraints,
    )
    dbm.create_table(
        "DurabilityDB",
        "Orders",
        schema_orders,
        order=4,
        search_key="order_id",
        constraints=orders_constraints,
    )
    users = dbm.get_table("DurabilityDB", "Users")
    products = dbm.get_table("DurabilityDB", "Products")
    orders = dbm.get_table("DurabilityDB", "Orders")
    return users, products, orders


def main():
    if os.path.exists(log_path()):
        os.remove(log_path())

    dbm = DatabaseManager(log_path=log_path())
    users, products, orders = setup_db(dbm)

    tx_id = dbm.begin()
    users.insert({"user_id": 1, "name": "Ada", "balance": 100}, tx_id=tx_id)
    products.insert({"product_id": 10, "name": "Widget", "stock": 5, "price": 10}, tx_id=tx_id)
    orders.insert({"order_id": 300, "user_id": 1, "product_id": 10, "qty": 1, "total": 10}, tx_id=tx_id)
    dbm.commit(tx_id)

    dbm = DatabaseManager(log_path=log_path())
    users, products, orders = setup_db(dbm)

    user = users.get(1)
    product = products.get(10)
    order = orders.get(300)

    if user and product and order:
        print("PASS: durability verified (committed data recovered).")
        return 0

    print("FAIL: durability error.")
    print("Users:", users.get_all())
    print("Products:", products.get_all())
    print("Orders:", orders.get_all())
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
