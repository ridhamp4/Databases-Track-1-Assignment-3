from flask import Blueprint, request, jsonify, make_response
from database.db_manager import DatabaseManager

api_bp = Blueprint('api', __name__)
db_manager = DatabaseManager()

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
