"""Hash de contraseñas y emision/validacion de JWT."""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

JWT_ALGORITHM = "HS256"
JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "720"))


def _secret() -> str:
    if not JWT_SECRET:
        # Deliberadamente explota en vez de generar uno al azar: con dos
        # instancias detras del ALB, un secreto por proceso haria que el token
        # emitido por una fuera rechazado por la otra, con fallos intermitentes
        # imposibles de diagnosticar. Ver .env.example.
        raise RuntimeError("JWT_SECRET no esta configurada")
    return JWT_SECRET


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Hash con formato invalido: tratarlo como contraseña incorrecta.
        return False


def create_access_token(id_usuario: int, username: str, es_admin: bool) -> str:
    ahora = datetime.now(timezone.utc)
    payload = {
        "sub": str(id_usuario),
        "username": username,
        "admin": es_admin,
        "iat": ahora,
        "exp": ahora + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
