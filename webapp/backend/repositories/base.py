"""Base repository -- shared connection helper."""
import sqlite3

from database.db import get_db


class BaseRepository:
    def _get_conn(self) -> sqlite3.Connection:
        return get_db()
