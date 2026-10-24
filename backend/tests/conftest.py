import os
import tempfile
from pathlib import Path

import pytest

# Point the app at a throwaway database before backend.database is imported.
_test_db_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{(Path(_test_db_dir) / 'test.db').as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402

from backend.database import Base, engine  # noqa: E402
from backend.main import app  # noqa: E402


def sign_in(test_client, name, phone):
    token = test_client.post("/auth/signin", json={"name": name, "phone": phone}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client():
    # Fresh tables for every test; the client is signed in as Asha by default.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        test_client.headers.update(sign_in(test_client, "Asha", "9000000001"))
        yield test_client
