import os
from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import declarative_base, sessionmaker


# Default to a file next to the project root so the DB does not depend on the current directory.
DEFAULT_DATABASE_PATH = Path(__file__).resolve().parent.parent / "splitwise.db"
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"

# Hosted Postgres (Neon, Render) hands out postgres:// URLs; SQLAlchemy needs the driver named.
for prefix in ("postgres://", "postgresql://"):
    if DATABASE_URL.startswith(prefix):
        DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len(prefix):]

IS_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    # SQLite connections may be used by different request-handling threads.
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
    # Free hosted databases drop idle connections; check before using one.
    pool_pre_ping=True,
)


if IS_SQLITE:
    # SQLite ignores foreign keys unless enabled on every connection.
    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# Columns added after the first release, so older databases can be upgraded in place.
NEW_COLUMNS = {
    "expense_shares": {"status": "VARCHAR NOT NULL DEFAULT 'accepted'"},
    "members": {"user_id": "INTEGER REFERENCES users(id)"},
    "groups": {"invite_code": "VARCHAR"},
    "settlements": {"status": "VARCHAR NOT NULL DEFAULT 'confirmed'"},
}


def add_missing_columns():
    """Add columns introduced after a user's database was created (create_all skips existing tables)."""
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table, columns in NEW_COLUMNS.items():
            if not inspector.has_table(table):
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, definition in columns.items():
                if name not in existing:
                    connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
