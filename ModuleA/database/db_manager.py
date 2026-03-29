class DatabaseManager:
    def __init__(self):
        self.databases = {}

    def create_database(self, db_name):
        if db_name not in self.databases:
            self.databases[db_name] = {}
            return True
        return False

    def delete_database(self, db_name):
        if db_name in self.databases:
            del self.databases[db_name]
            return True
        return False

    def list_databases(self):
        return list(self.databases.keys())

    def create_table(self, db_name, table_name, schema, order, search_key):
        if db_name not in self.databases:
            return False
        if table_name not in self.databases[db_name]:
            from .table import Table
            self.databases[db_name][table_name] = Table(table_name, schema, order, search_key)
            return True
        return False

    def delete_table(self, db_name, table_name):
        if db_name in self.databases and table_name in self.databases[db_name]:
            del self.databases[db_name][table_name]
            return True
        return False

    def list_tables(self, db_name):
        if db_name in self.databases:
            return list(self.databases[db_name].keys())
        return []

    def get_table(self, db_name, table_name):
        if db_name in self.databases:
            return self.databases[db_name].get(table_name)
        return None
