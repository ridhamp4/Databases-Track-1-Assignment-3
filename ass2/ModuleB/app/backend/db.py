import mysql.connector
import config


def get_db():
    return mysql.connector.connect(
        host=config.MYSQL_HOST,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
        database=config.MYSQL_DB,
    )


def query_db(sql, args=None, one=False):
    conn = get_db()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, args or ())
        rows = cursor.fetchall()
        cursor.close()
        if one:
            return rows[0] if rows else None
        return rows
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _set_audit_session_vars(cursor):
    """Set MySQL session variables so triggers can identify API-based operations."""
    try:
        from flask import request as flask_request, has_request_context, g
        from flask_jwt_extended import get_jwt_identity
        if has_request_context():
            username = 'anonymous'
            try:
                uid = get_jwt_identity()
                if uid:
                    # Cache username in Flask g to avoid repeated SELECTs
                    if hasattr(g, '_audit_username'):
                        username = g._audit_username
                    else:
                        conn2 = get_db()
                        c2 = conn2.cursor(buffered=True)
                        c2.execute("SELECT Username FROM Member WHERE MemberID = %s", (int(uid),))
                        row = c2.fetchone()
                        if row:
                            username = row[0]
                        c2.close()
                        conn2.close()
                        g._audit_username = username
            except Exception:
                pass
            cursor.execute("SET @app_username = %s", (username,))
            cursor.execute("SET @app_endpoint = %s", (flask_request.path,))
            cursor.execute("SET @app_ip = %s", (flask_request.remote_addr or '127.0.0.1',))
    except Exception:
        pass


def execute_db(sql, args=None):
    conn = get_db()
    try:
        cursor = conn.cursor(buffered=True)
        _set_audit_session_vars(cursor)
        cursor.execute(sql, args or ())
        conn.commit()
        last_id = cursor.lastrowid
        cursor.close()
        return last_id
    finally:
        try:
            conn.close()
        except Exception:
            pass


def execute_transaction(statements):
    """Execute multiple SQL statements in a single transaction.
    statements is a list of (sql, args) tuples.
    Returns the lastrowid of the final statement."""
    conn = get_db()
    try:
        cursor = conn.cursor(buffered=True)
        _set_audit_session_vars(cursor)
        last_id = None
        for sql, args in statements:
            cursor.execute(sql, args or ())
            last_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        return last_id
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass
