import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker


# Default to a file next to the project root so the DB does not depend on the current directory.
DEFAULT_DATABASE_PATH = Path(__file__).resolve().parent.parent / "splitwise.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}")

engine = create_engine(
    DATABASE_URL,
    # SQLite connections may be used by different request-handling threads.
    connect_args={"check_same_thread": False},
)


# SQLite ignores foreign keys unless enabled on every connection.
@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
