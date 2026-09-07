"""Dependencias compartidas de FastAPI: sesion de base y usuario autenticado."""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Cliente, Profesional, Usuario
from app.security import decode_access_token

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_db():
    yield from get_session()


def get_current_usuario(
    token: Optional[str] = Depends(oauth2),
    db: Session = Depends(get_db),
) -> Usuario:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta el token de acceso",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido o vencido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    usuario = db.get(Usuario, int(payload["sub"]))
    if usuario is None:
        raise HTTPException(status_code=401, detail="El usuario del token ya no existe")

    # La baja logica de la cuenta tiene que cortar el acceso aunque el token
    # siga siendo criptograficamente valido.
    if not usuario.cuenta.activo:
        raise HTTPException(status_code=403, detail="La cuenta esta desactivada")

    return usuario


def get_current_cliente(usuario: Usuario = Depends(get_current_usuario)) -> Cliente:
    if usuario.cliente is None:
        raise HTTPException(status_code=403, detail="El usuario no esta registrado como cliente")
    return usuario.cliente


def get_current_profesional(usuario: Usuario = Depends(get_current_usuario)) -> Profesional:
    if usuario.profesional is None:
        raise HTTPException(status_code=403, detail="El usuario no esta registrado como profesional")
    return usuario.profesional


def require_admin(usuario: Usuario = Depends(get_current_usuario)) -> Usuario:
    if not usuario.cuenta.es_admin:
        raise HTTPException(status_code=403, detail="Requiere permisos de administrador")
    return usuario


def usuario_out(usuario: Usuario) -> dict:
    """Arma el UsuarioOut aplanando cuenta y subtipos."""
    return {
        "id_usuario": usuario.id_usuario,
        "nombre": usuario.nombre,
        "apellido": usuario.apellido,
        "email": usuario.email,
        "telefono": usuario.telefono,
        "fecha_registro": usuario.fecha_registro,
        "es_cliente": usuario.cliente is not None,
        "es_profesional": usuario.profesional is not None,
        "es_admin": usuario.cuenta.es_admin,
        "activo": usuario.cuenta.activo,
    }
