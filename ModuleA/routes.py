from flask import Blueprint, request, jsonify, make_response
from database.db_manager import DatabaseManager
from database.transaction_manager import TransactionManager

api_bp = Blueprint('api', __name__)
db_manager = DatabaseManager()
txn_manager = TransactionManager(db_manager)

# ─────────────────────────────────────────────
# Original CRUD endpoints (unchanged)
# ─────────────────────────────────────────────

@api_bp.route('/databases', methods=['GET'])
def list_databases():
    return jsonify(db_manager.list_databases()), 200

@api_bp.route('/databases', methods=['POST'])
def create_database():
    data = request.json
    db_name = data.get('db_name')
    if not db_name:
        return jsonify({'error': 'db_name required'}), 400
    if db_manager.create_database(db_name):
        return jsonify({'message': 'Database created', 'db_name': db_name}), 201
    return jsonify({'error': 'Database already exists'}), 400

@api_bp.route('/databases/<db_name>', methods=['DELETE'])
def delete_database(db_name):
    if db_manager.delete_database(db_name):
        return jsonify({'message': 'Database deleted'}), 200
    return jsonify({'error': 'Database not found'}), 404

@api_bp.route('/databases/<db_name>/tables', methods=['GET'])
def list_tables(db_name):
    if db_name not in db_manager.databases:
        return jsonify({'error': 'Database not found'}), 404
    return jsonify(db_manager.list_tables(db_name)), 200

@api_bp.route('/databases/<db_name>/tables', methods=['POST'])
def create_table(db_name):
    data = request.json
    table_name = data.get('table_name')
    schema = data.get('schema', {})
    order = data.get('order', 8)
    search_key = data.get('search_key')

    if not all([table_name, search_key]):
        return jsonify({'error': 'table_name and search_key required'}), 400

    if db_manager.create_table(db_name, table_name, schema, order, search_key):
        return jsonify({'message': 'Table created'}), 201
    return jsonify({'error': 'Database not found or table exists'}), 400

@api_bp.route('/databases/<db_name>/tables/<table_name>', methods=['DELETE'])
def delete_table(db_name, table_name):
    if db_manager.delete_table(db_name, table_name):
        return jsonify({'message': 'Table deleted'}), 200
    return jsonify({'error': 'Not found'}), 404

@api_bp.route('/databases/<db_name>/tables/<table_name>/records', methods=['POST'])
def insert_record(db_name, table_name):
    table = db_manager.get_table(db_name, table_name)
    if not table:
        return jsonify({'error': 'Table not found'}), 404

    try:
        table.insert(request.json)
        return jsonify({'message': 'Record inserted'}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

@api_bp.route('/databases/<db_name>/tables/<table_name>/records', methods=['GET'])
def get_all_records(db_name, table_name):
    table = db_manager.get_table(db_name, table_name)
    if not table:
        return jsonify({'error': 'Table not found'}), 404
    return jsonify(table.get_all()), 200

@api_bp.route('/databases/<db_name>/tables/<table_name>/records/<record_id>', methods=['GET'])
def get_record(db_name, table_name, record_id):
    table = db_manager.get_table(db_name, table_name)
    if not table:
        return jsonify({'error': 'Table not found'}), 404

    try:
        rec_id = int(record_id)
    except ValueError:
        rec_id = record_id

    record = table.get(rec_id)
    if not record and isinstance(rec_id, int):
        record = table.get(str(record_id))

    if record:
        return jsonify(record), 200
    return jsonify({'error': 'Record not found'}), 404

@api_bp.route('/databases/<db_name>/tables/<table_name>/records/<record_id>', methods=['PUT'])
def update_record(db_name, table_name, record_id):
    table = db_manager.get_table(db_name, table_name)
    if not table:
        return jsonify({'error': 'Table not found'}), 404

    try:
        rec_id = int(record_id)
    except ValueError:
        rec_id = record_id

    try:
        if table.update(rec_id, request.json):
            return jsonify({'message': 'Record updated'}), 200
        return jsonify({'error': 'Record not found'}), 404
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

@api_bp.route('/databases/<db_name>/tables/<table_name>/records/<record_id>', methods=['DELETE'])
def delete_record(db_name, table_name, record_id):
    table = db_manager.get_table(db_name, table_name)
    if not table:
        return jsonify({'error': 'Table not found'}), 404

    try:
        rec_id = int(record_id)
    except ValueError:
        rec_id = record_id

    if table.delete(rec_id):
        return jsonify({'message': 'Record deleted'}), 200
    return jsonify({'error': 'Record not found'}), 404

@api_bp.route('/databases/<db_name>/tables/<table_name>/search', methods=['POST'])
def search_records(db_name, table_name):
    table = db_manager.get_table(db_name, table_name)
    if not table:
        return jsonify({'error': 'Table not found'}), 404

    constraints = request.json
    return jsonify(table.search(constraints)), 200

@api_bp.route('/databases/<db_name>/tables/<table_name>/range', methods=['GET'])
def range_query(db_name, table_name):
    table = db_manager.get_table(db_name, table_name)
    if not table:
        return jsonify({'error': 'Table not found'}), 404

    field = request.args.get('field')
    start = request.args.get('start')
    end = request.args.get('end')

    if not all([field, start, end]):
        return jsonify({'error': 'field, start, end required parameters'}), 400

    try: start = int(start)
    except ValueError: pass
    try: end = int(end)
    except ValueError: pass

    return jsonify(table.range_query(field, start, end)), 200

@api_bp.route('/databases/<db_name>/tables/<table_name>/visualize', methods=['GET'])
def visualize_tree(db_name, table_name):
    table = db_manager.get_table(db_name, table_name)
    if not table:
        return jsonify({'error': 'Table not found'}), 404

    dot = table.data.visualize_tree()
    svg = dot.pipe(format='svg')
    response = make_response(svg)
    response.content_type = 'image/svg+xml'
    return response


# ─────────────────────────────────────────────
# Transaction Management Endpoints
# ─────────────────────────────────────────────

@api_bp.route('/transactions', methods=['POST'])
def begin_transaction():
    """Begin a new transaction."""
    txn_id = txn_manager.begin()
    return jsonify({'txn_id': txn_id, 'message': 'Transaction started'}), 201

@api_bp.route('/transactions/<txn_id>/commit', methods=['POST'])
def commit_transaction(txn_id):
    """Commit a transaction."""
    try:
        txn_manager.commit(txn_id)
        return jsonify({'txn_id': txn_id, 'message': 'Transaction committed'}), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

@api_bp.route('/transactions/<txn_id>/rollback', methods=['POST'])
def rollback_transaction(txn_id):
    """Rollback a transaction."""
    try:
        txn_manager.rollback(txn_id)
        return jsonify({'txn_id': txn_id, 'message': 'Transaction rolled back'}), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

@api_bp.route('/transactions', methods=['GET'])
def list_transactions():
    """List active transactions."""
    return jsonify(txn_manager.get_active_transactions()), 200

@api_bp.route('/transactions/<txn_id>/insert', methods=['POST'])
def txn_insert(txn_id):
    """Insert a record within a transaction."""
    data = request.json
    db_name = data.get('db_name')
    table_name = data.get('table_name')
    record = data.get('record')

    if not all([db_name, table_name, record]):
        return jsonify({'error': 'db_name, table_name, and record required'}), 400

    try:
        txn_manager.insert(txn_id, db_name, table_name, record)
        return jsonify({'message': 'Record inserted in transaction'}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

@api_bp.route('/transactions/<txn_id>/update', methods=['POST'])
def txn_update(txn_id):
    """Update a record within a transaction."""
    data = request.json
    db_name = data.get('db_name')
    table_name = data.get('table_name')
    key = data.get('key')
    record = data.get('record')

    if not all([db_name, table_name, key is not None, record]):
        return jsonify({'error': 'db_name, table_name, key, and record required'}), 400

    try:
        try:
            key = int(key)
        except (ValueError, TypeError):
            pass
        txn_manager.update(txn_id, db_name, table_name, key, record)
        return jsonify({'message': 'Record updated in transaction'}), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

@api_bp.route('/transactions/<txn_id>/delete', methods=['POST'])
def txn_delete(txn_id):
    """Delete a record within a transaction."""
    data = request.json
    db_name = data.get('db_name')
    table_name = data.get('table_name')
    key = data.get('key')

    if not all([db_name, table_name, key is not None]):
        return jsonify({'error': 'db_name, table_name, and key required'}), 400

    try:
        try:
            key = int(key)
        except (ValueError, TypeError):
            pass
        txn_manager.delete(txn_id, db_name, table_name, key)
        return jsonify({'message': 'Record deleted in transaction'}), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


# ─────────────────────────────────────────────
# Recovery & WAL Endpoints
# ─────────────────────────────────────────────

@api_bp.route('/recovery', methods=['POST'])
def crash_recovery():
    """Perform crash recovery from WAL."""
    report = txn_manager.recover()
    return jsonify({'message': 'Recovery completed', 'report': report}), 200

@api_bp.route('/checkpoint', methods=['POST'])
def create_checkpoint():
    """Create a checkpoint (snapshot + truncate WAL)."""
    snapshot = txn_manager.checkpoint()
    return jsonify({
        'message': 'Checkpoint created',
        'databases': list(snapshot.keys()),
    }), 200

@api_bp.route('/wal', methods=['GET'])
def view_wal():
    """View WAL entries."""
    entries = txn_manager.get_wal_entries()
    return jsonify({'entries': entries, 'count': len(entries)}), 200

@api_bp.route('/wal', methods=['DELETE'])
def clear_wal():
    """Clear the WAL (for testing)."""
    txn_manager.wal.clear()
    return jsonify({'message': 'WAL cleared'}), 200
