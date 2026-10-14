"""Точка входа Passenger (виртуальный хостинг): FastAPI — ASGI-приложение, Passenger ждёт WSGI — переходник a2wsgi."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a2wsgi import ASGIMiddleware  # noqa: E402

from app.main import app  # noqa: E402

application = ASGIMiddleware(app)
