"""Хранение результата синхронизации в SQLite.

Телефон — первичный ключ таблицы клиентов: дубль в хранилище невозможен структурно, а не только
благодаря коду. Синхронизация заменяет снимок целиком в одной транзакции — повторный запуск по тем же
заявкам даёт ту же таблицу, а читатель никогда не видит половину старого и половину нового.
"""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .merge import MergeResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    phone    TEXT PRIMARY KEY,
    name     TEXT NOT NULL,
    email    TEXT NOT NULL,
    amount   TEXT NOT NULL,      -- JSON-число: int остаётся int, дробь — дробью
    position INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sync_state (
    id        INTEGER PRIMARY KEY CHECK (id = 1),
    stats     TEXT NOT NULL,
    synced_at TEXT NOT NULL
);
"""


class Storage:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def save(self, result: MergeResult) -> None:
        """Заменяет сохранённый снимок результатом синхронизации."""
        synced_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM clients")
            conn.executemany(
                "INSERT INTO clients (phone, name, email, amount, position) VALUES (?, ?, ?, ?, ?)",
                [(c.phone, c.name, c.email, json.dumps(c.amount), c.position) for c in result.clients],
            )
            conn.execute(
                "INSERT INTO sync_state (id, stats, synced_at) VALUES (1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET stats = excluded.stats, synced_at = excluded.synced_at",
                (json.dumps(result.stats()), synced_at),
            )

    def load(self) -> tuple[dict, str] | None:
        """Сохранённый результат в формате ответа и время синхронизации; None, если её ещё не было."""
        with closing(self._connect()) as conn:
            state = conn.execute("SELECT stats, synced_at FROM sync_state WHERE id = 1").fetchone()
            if state is None:
                return None
            rows = conn.execute("SELECT name, phone, email, amount FROM clients ORDER BY position").fetchall()
        clients = [
            {"name": name, "phone": phone, "email": email, "amount": json.loads(amount)}
            for name, phone, email, amount in rows
        ]
        return {"clients": clients, "stats": json.loads(state[0])}, state[1]
