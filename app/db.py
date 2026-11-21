from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

# Configure SQLite engine with busy_timeout for concurrency
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False, "timeout": 30}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    future=True,
)

if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=DELETE")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)


def verify_schema():
    """Fail loud if the on-disk schema does not match the models (there are no
    migrations: an old database must be migrated or archived by hand)."""
    from sqlalchemy import inspect
    import app.models  # noqa: F401

    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            raise RuntimeError(f"Missing table {table.name!r}")
        on_disk = {c["name"] for c in insp.get_columns(table.name)}
        expected = {c.name for c in table.columns}
        if on_disk != expected:
            raise RuntimeError(
                f"Schema mismatch for table {table.name!r}: missing={sorted(expected - on_disk)}, "
                f"unexpected={sorted(on_disk - expected)}. Refusing to start."
            )
