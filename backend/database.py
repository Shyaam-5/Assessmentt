"""Async-compatible MySQL connection pool using synchronous PyMySQL under the hood.

aiomysql/asyncmy fail with TiDB Cloud TLS on Windows, so we wrap PyMySQL
connections with asyncio.to_thread to keep the FastAPI route interface async.

The public API is identical to the previous aiomysql-based version:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT ...")
            rows = await cur.fetchall()
"""

import asyncio
import ssl as _ssl
from contextlib import asynccontextmanager

import pymysql
import pymysql.cursors

from config import settings

# ─── Global pool ────────────────────────────────────────────────

_pool: "PyMySQLPool | None" = None


class _AsyncCursorWrapper:
    """Wraps a synchronous pymysql cursor so callers can ``await`` its methods."""

    def __init__(self, sync_cursor):
        self._cur = sync_cursor

    async def execute(self, query, args=None):
        return await asyncio.to_thread(self._cur.execute, query, args)

    async def executemany(self, query, args):
        return await asyncio.to_thread(self._cur.executemany, query, args)

    async def fetchone(self):
        return await asyncio.to_thread(self._cur.fetchone)

    async def fetchall(self):
        return await asyncio.to_thread(self._cur.fetchall)

    async def fetchmany(self, size=None):
        return await asyncio.to_thread(self._cur.fetchmany, size)

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def description(self):
        return self._cur.description

    # Context-manager support (async with conn.cursor() as cur)
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._cur.close()
        return False


class _AsyncConnectionWrapper:
    """Wraps a synchronous pymysql connection so callers can use"""

    def __init__(self, sync_conn):
        self._conn = sync_conn

    def cursor(self, cursor_class=None):
        """Return an async-wrapped cursor.

        ``cursor_class`` is accepted for API compatibility with aiomysql
        (e.g. ``aiomysql.DictCursor``), but we always use pymysql's own
        DictCursor when the caller requests one.
        """
        # Map aiomysql.DictCursor → pymysql.cursors.DictCursor
        if cursor_class is not None:
            cls_name = getattr(cursor_class, "__name__", "")
            if "Dict" in cls_name:
                cursor_class = pymysql.cursors.DictCursor
        raw = self._conn.cursor(cursor_class or pymysql.cursors.DictCursor)
        return _AsyncCursorWrapper(raw)

    async def commit(self):
        await asyncio.to_thread(self._conn.commit)

    async def rollback(self):
        await asyncio.to_thread(self._conn.rollback)

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    # Context-manager support (async with conn.cursor(...) as cur)
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


class PyMySQLPool:
    """Minimal async-compatible connection pool backed by PyMySQL."""

    def __init__(self, connect_kwargs: dict, maxsize: int = 10):
        self._connect_kwargs = connect_kwargs
        self._maxsize = maxsize

    def _create_connection(self):
        return pymysql.connect(**self._connect_kwargs)

    @asynccontextmanager
    async def acquire(self):
        """Yield an async-wrapped connection (mirrors aiomysql pool.acquire)."""
        conn = await asyncio.to_thread(self._create_connection)
        wrapper = _AsyncConnectionWrapper(conn)
        try:
            yield wrapper
        finally:
            wrapper.close()

    def close(self):
        pass  # Each connection is closed after use

    async def wait_closed(self):
        pass


# ─── Public helpers ─────────────────────────────────────────────

async def get_pool() -> PyMySQLPool:
    """Return the pool or raise if not initialised."""
    if _pool is None:
        raise RuntimeError("Database pool not initialised – call init_db() first.")
    return _pool


async def init_db() -> None:
    """Create the global connection pool at application startup."""
    global _pool

    ssl_ctx = _ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = _ssl.CERT_NONE

    connect_kwargs = dict(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        ssl=ssl_ctx,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=15,
        cursorclass=pymysql.cursors.DictCursor,
    )

    # Verify connection works at startup
    test_conn = await asyncio.to_thread(pymysql.connect, **connect_kwargs)
    test_conn.close()

    _pool = PyMySQLPool(connect_kwargs, maxsize=10)
    print(f"[OK] Database pool created - {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")


async def close_db() -> None:
    """Clean up on shutdown."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
        print("[OK] Database pool closed.")
