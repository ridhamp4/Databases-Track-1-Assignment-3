from .bplustree import BPlusTree

class Table:
    def __init__(self, name, schema, order, search_key):
        self.name = name
        self.schema = schema
        self.search_key = search_key
        self.data = BPlusTree(order=order)

    def validate_record(self, record):
        if not isinstance(record, dict):
            raise ValueError("Record must be a dictionary")
        if self.search_key not in record:
            raise ValueError(f"Record must contain search key: {self.search_key}")
        for field, schema_type in self.schema.items():
            if field in record:
                # We can add specialized schema checking here if needed
                pass
        return True

    def insert(self, record):
        self.validate_record(record)
        key = record[self.search_key]
        self.data.insert(key, record)

    def get(self, record_id):
        return self.data.search(record_id)

    def get_all(self):
        return [v for k, v in self.data.get_all()]

    def search(self, constraints):
        results = []
        for key, record in self.data.get_all():
            match = True
            for k, v in constraints.items():
                if record.get(k) != v:
                    match = False
                    break
            if match:
                results.append(record)
        return results

    def delete(self, record_id):
        return self.data.delete(record_id)

    def update(self, record_id, new_record):
        self.validate_record(new_record)
        return self.data.update(record_id, new_record)

    def range_query(self, field, start_value, end_value):
        if field == self.search_key:
            results = self.data.range_query(start_value, end_value)
            return [v for k, v in results]
        else:
            results = []
            for k, record in self.data.get_all():
                val = record.get(field)
                if val is not None and start_value <= val <= end_value:
                    results.append(record)
            return results
