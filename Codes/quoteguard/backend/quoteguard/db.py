from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(get_settings().DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20, future=True)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=True)
    return _engine


def SessionLocal() -> Session:
    engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def reset_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


@contextmanager
def session_scope() -> Iterator[Session]:
    """A short unit of work. Never hold one open across an external API call."""
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
