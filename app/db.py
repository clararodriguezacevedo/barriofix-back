"""Conexion a PostgreSQL en RDS.

La URL completa lleva la password, asi que sale siempre de DATABASE_URL y nunca
se hardcodea: este repo es publico. Ver .env.example.

El engine se crea perezosamente para que la app siga levantando aunque la base
no este configurada todavia. Sin eso, un DATABASE_URL vacio o una AMI sin
SQLAlchemy instalado tiraria abajo el proceso entero en el import y el Target
Group sacaria la instancia del ALB.
"""

import os
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "")

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL no esta configurada (ver .env.example)")
        _engine = create_engine(
            DATABASE_URL,
            # RDS corta las conexiones ociosas; sin esto la primera query despues
            # de un rato de inactividad falla con "server closed the connection".
            pool_pre_ping=True,
            pool_recycle=1800,
            pool_size=5,
            max_overflow=5,
        )
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def get_session() -> Session:
    """Dependencia de FastAPI: una sesion por request, cerrada al terminar."""
    get_engine()
    assert _SessionLocal is not None
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_connection() -> dict:
    """Prueba de vida de la base. La usa GET /health/db."""
    with get_engine().connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar_one()
        tablas = conn.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
        ).scalar_one()
    return {"status": "ok", "version": version.split(",")[0], "tablas": tablas}
