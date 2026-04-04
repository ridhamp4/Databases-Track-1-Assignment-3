import os
import threading
import time

from database.db_manager import DatabaseManager


def log_path():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "isolation.log"))


def setup_db(dbm):
    dbm.create_database("IsolationDB")
    schema_users = {"user_id": "int", "name": "str", "balance": "int"}
    users_constraints = {"non_negative": ["balance"]}
    dbm.create_table(
        "IsolationDB",
        "Users",
        schema_users,
        order=4,
        search_key="user_id",
        constraints=users_constraints,
    )
    users = dbm.get_table("IsolationDB", "Users")
    return users


def worker(dbm, users, delay, results, index):
    tx_id = dbm.begin()
    user = users.get(1)
    new_user = dict(user)
    new_user["balance"] = user["balance"] - 10
    time.sleep(delay)
    users.update(1, new_user, tx_id=tx_id)
    dbm.commit(tx_id)
    results[index] = new_user["balance"]


def main():
    if os.path.exists(log_path()):
        os.remove(log_path())

    dbm = DatabaseManager(log_path=log_path())
    users = setup_db(dbm)
    users.insert({"user_id": 1, "name": "Ada", "balance": 100})

    results = [None, None]
    t1 = threading.Thread(target=worker, args=(dbm, users, 0.5, results, 0))
    t2 = threading.Thread(target=worker, args=(dbm, users, 0.1, results, 1))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    final_user = users.get(1)
    if final_user is None:
        print("FAIL: missing user record.")
        return 1

    if final_user["balance"] == 80:
        print("PASS: isolation verified (serializable outcome).")
        return 0

    print("FAIL: isolation error, final balance:", final_user["balance"])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
