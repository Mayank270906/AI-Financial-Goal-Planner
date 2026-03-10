import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()


def _running_in_container() -> bool:
    return os.path.exists("/.dockerenv")


def _normalize_database_url(database_url: str) -> str:
    # Trim accidental whitespace/quotes often introduced by env editors.
    normalized = database_url.strip().strip('"').strip("'")

    # Some providers still expose postgres://; SQLAlchemy expects postgresql://.
    if normalized.startswith("postgres://"):
        normalized = "postgresql://" + normalized[len("postgres://"):]

    parsed_url = make_url(normalized)
    host = (parsed_url.host or "").lower()

    # Supabase requires SSL for direct DB and pooler host connections.
    if (host.endswith(".supabase.co") or host.endswith(".supabase.com")) and "sslmode" not in parsed_url.query:
        separator = "&" if "?" in normalized else "?"
        normalized = f"{normalized}{separator}sslmode=require"

    return normalized


def _get_database_url() -> str:
    database_url = (
        os.getenv("SQLALCHEMY_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("SUPABASE_DB_URL")
    )
    if not database_url:
        raise RuntimeError("SQLALCHEMY_DATABASE_URL is not set")

    database_url = _normalize_database_url(database_url)

    # In containers, localhost points to the app container itself, not your DB host.
    if _running_in_container():
        parsed_url = make_url(database_url)
        host = (parsed_url.host or "").lower()
        if host in {"localhost", "127.0.0.1"}:
            raise RuntimeError(
                "Database host is set to localhost inside a container. "
                "Set SQLALCHEMY_DATABASE_URL with a reachable DB host "
                "(for example, a managed database hostname)."
            )

    return database_url


SQLALCHEMY_DATABASE_URL = _get_database_url()

engine_kwargs = {}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_pre_ping"] = True

engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()