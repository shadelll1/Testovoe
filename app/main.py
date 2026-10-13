"""HTTP-сервис: забирает заявки из источника, схлопывает дубли и отдаёт клиентов."""

import logging
import os
import threading

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .merge import merge_orders
from .storage import Storage

SOURCE_URL = os.environ.get("SOURCE_URL", "https://test.ooobs.ru/api/orders")
DB_PATH = os.environ.get("DB_PATH", "data/sync.sqlite3")
SOURCE_TIMEOUT = float(os.environ.get("SOURCE_TIMEOUT", "10"))

log = logging.getLogger("orders_sync")

app = FastAPI(title="orders-sync", docs_url=None, redoc_url=None)
storage = Storage(DB_PATH)
_sync_lock = threading.Lock()


class SourceError(Exception):
    pass


def fetch_orders() -> list:
    """Заявки из источника. Ответ не JSON-массив — ошибка, а не пустой список: иначе мусор затёр бы результат."""
    try:
        response = httpx.get(SOURCE_URL, timeout=SOURCE_TIMEOUT, headers={"Cache-Control": "no-cache"})
        response.raise_for_status()
        orders = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise SourceError(f"источник недоступен: {exc}") from exc
    if not isinstance(orders, list):
        raise SourceError("источник вернул не JSON-массив")
    return orders


def sync() -> dict:
    """Синхронизация: заявки → нормализация и дедупликация → снимок в базе. Возвращает сохранённый результат."""
    with _sync_lock:
        storage.save(merge_orders(fetch_orders()))
        result, _ = storage.load()
        return result


def _clients_response() -> JSONResponse:
    """Свежий результат; если источник лёг — последний сохранённый с заголовком X-Data-Stale."""
    try:
        return JSONResponse(sync())
    except SourceError as exc:
        log.warning("%s", exc)
        saved = storage.load()
        if saved is None:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        result, synced_at = saved
        return JSONResponse(result, headers={"X-Data-Stale": synced_at})


@app.get("/")
def root() -> JSONResponse:
    return _clients_response()


@app.get("/api/clients")
def clients() -> JSONResponse:
    return _clients_response()


@app.post("/api/sync")
def run_sync() -> JSONResponse:
    try:
        return JSONResponse(sync())
    except SourceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
