import io
import json
from wsgiref.util import setup_testing_defaults

import passenger_wsgi
from app import main
from app.storage import Storage
from tests.test_api import EXPECTED, SAMPLE


def test_passenger_entry_point(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "storage", Storage(tmp_path / "db.sqlite3"))
    monkeypatch.setattr(main, "fetch_orders", lambda: SAMPLE)
    environ = {"PATH_INFO": "/api/clients", "wsgi.input": io.BytesIO()}
    setup_testing_defaults(environ)
    status = []
    body = b"".join(passenger_wsgi.application(environ, lambda s, h, exc=None: status.append(s)))
    assert status == ["200 OK"]
    assert json.loads(body) == EXPECTED
