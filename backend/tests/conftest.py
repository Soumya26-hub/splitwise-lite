import os
import tempfile
from pathlib import Path

import pytest

# Point the app at a throwaway database before backend.database is imported.
_test_db_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{(Path(_test_db_dir) / 'test.db').as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402

from backend.database import Base, SessionLocal, engine  # noqa: E402
from backend.main import app  # noqa: E402
from backend.seed_data import seed_if_empty  # noqa: E402


@pytest.fixture
def client():
    # Fresh, re-seeded tables for every test.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()
    with TestClient(app) as test_client:
        yield test_client
