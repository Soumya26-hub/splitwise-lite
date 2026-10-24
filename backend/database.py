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


def add_missing_columns():
    """Add columns introduced after a user's database was created (create_all skips existing tables)."""
    with engine.begin() as connection:
        columns = [row[1] for row in connection.exec_driver_sql("PRAGMA table_info(expense_shares)")]
        if columns and "status" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE expense_shares ADD COLUMN status VARCHAR NOT NULL DEFAULT 'accepted'"
            )


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
