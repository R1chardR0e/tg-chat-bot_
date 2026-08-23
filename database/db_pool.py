import sqlite3
import threading
from contextlib import contextmanager

from config import DB_PATH


class DatabasePool:
    def __init__(self, db_path, pool_size=5):
        self.db_path = db_path
        self.pool_size = pool_size
        self.pool = []
        self.lock = threading.Lock()
        self._initialize_pool()

    def _initialize_pool(self):
        """Initialize the connection pool with database connections."""
        for _ in range(self.pool_size):
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row  # Enable dict-like access to rows
            self.pool.append(conn)

    def get_connection(self):
        """Get a connection from the pool."""
        with self.lock:
            if self.pool:
                return self.pool.pop()
            else:
                # При пустом пуле создаётся новое соединение.
                conn = sqlite3.connect(self.db_path, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                return conn

    def return_connection(self, conn):
        """Return a connection to the pool."""
        with self.lock:
            if len(self.pool) < self.pool_size:
                self.pool.append(conn)
            else:
                # Лишнее соединение закрывается, если пул уже заполнен.
                conn.close()

    def close_all(self):
        """Close all connections in the pool."""
        with self.lock:
            for conn in self.pool:
                conn.close()
            self.pool.clear()


# Общий пул соединений приложения.
_pool = DatabasePool(DB_PATH)


@contextmanager
def db_connection_context():
    """Context manager for database connections from the pool."""
    conn = _pool.get_connection()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.return_connection(conn)


def get_db_connection():
    """Get a direct connection from the pool."""
    return _pool.get_connection()


def return_db_connection(conn):
    """Return a connection to the pool."""
    _pool.return_connection(conn)
