import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import SourceError
from app.storage import Storage

# Снимок /api/orders на 2026-10-13
SAMPLE = json.loads((Path(__file__).parent / "orders_sample.json").read_text(encoding="utf-8"))

EXPECTED = {
    "clients": [
        {"name": "Иван П.", "phone": "+79991234567", "email": "", "amount": 5000},
        {"name": "Мария С.", "phone": "+79160000001", "email": "maria@example.com", "amount": 200},
        {"name": "Олег Кузнецов", "phone": "+79031112233", "email": "", "amount": 7500},
        {"name": "Анна В.", "phone": "+79219998877", "email": "", "amount": 1500},
        {"name": "Павел Орлов", "phone": "+79005551212", "email": "pavel@example.com", "amount": 300},
        {"name": "Елена Морозова", "phone": "+79261234567", "email": "elena@example.com", "amount": 9000},
        {"name": "Сергей Зайцев", "phone": "+79991110000", "email": "sergey@example.com", "amount": 450},
        {"name": "Дмитрий Лебедев", "phone": "+79164455667", "email": "dmitry@example.com", "amount": 12000},
    ],
    "stats": {"received": 17, "unique": 8, "duplicates_merged": 5, "invalid_dropped": 4},
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "storage", Storage(tmp_path / "db.sqlite3"))
    monkeypatch.setattr(main, "fetch_orders", lambda: SAMPLE)
    return TestClient(main.app)


def test_result_matches_expected(client):
    assert client.get("/").json() == EXPECTED
    assert client.get("/api/clients").json() == EXPECTED


def test_repeated_sync_is_idempotent(client):
    for _ in range(3):
        assert client.post("/api/sync").json() == EXPECTED
    with sqlite3.connect(main.storage.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0] == 8


def test_source_down_serves_last_result(client, monkeypatch):
    client.post("/api/sync")

    def broken():
        raise SourceError("источник недоступен")

    monkeypatch.setattr(main, "fetch_orders", broken)
    response = client.get("/")
    assert response.json() == EXPECTED
    assert "X-Data-Stale" in response.headers
    assert client.post("/api/sync").status_code == 502


def test_source_down_before_first_sync(client, monkeypatch):
    def broken():
        raise SourceError("источник недоступен")

    monkeypatch.setattr(main, "fetch_orders", broken)
    assert client.get("/").status_code == 502
