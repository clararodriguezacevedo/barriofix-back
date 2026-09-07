"""Gestion de usuarios y sus roles.

Casi todo es backoffice: el alta la hace /api/auth/registro y la edicion del
perfil propio /api/auth/me.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import get_current_usuario, get_db, require_admin, usuario_out
from app.models import Cliente, Profesional, Usuario
from app.schemas import ActivoIn, ProfesionalUpdateIn, UsuarioOut

router = APIRouter(prefix="/api/usuarios", tags=["usuarios"])


def _get_usuario(db: Session, id_usuario: int) -> Usuario:
    usuario = db.get(Usuario, id_usuario)
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return usuario


@router.get("", response_model=List[UsuarioOut], dependencies=[Depends(require_admin)])
def listar(
    rol: Optional[str] = None,
    activo: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    stmt = select(Usuario)
    if rol == "cliente":
        stmt = stmt.join(Cliente, Cliente.id_usuario == Usuario.id_usuario)
    elif rol == "profesional":
        stmt = stmt.join(Profesional, Profesional.id_usuario == Usuario.id_usuario)

    usuarios = db.execute(stmt.order_by(Usuario.id_usuario)).scalars().all()
    if activo is not None:
        usuarios = [u for u in usuarios if u.cuenta.activo is activo]
    return [usuario_out(u) for u in usuarios]


@router.get("/{id_usuario}", response_model=UsuarioOut)
def obtener(
    id_usuario: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    return usuario_out(_get_usuario(db, id_usuario))


@router.patch(
    "/{id_usuario}/activo", response_model=UsuarioOut, dependencies=[Depends(require_admin)]
)
def cambiar_activo(id_usuario: int, payload: ActivoIn, db: Session = Depends(get_db)):
    """Baja logica: es la baja que se usa de verdad, porque conserva el
    historial de solicitudes y calificaciones."""
    usuario = _get_usuario(db, id_usuario)
    usuario.cuenta.activo = payload.activo
    db.commit()
    db.refresh(usuario)
    return usuario_out(usuario)


@router.delete("/{id_usuario}", status_code=204, dependencies=[Depends(require_admin)])
def borrar(id_usuario: int, db: Session = Depends(get_db)):
    """Borrado real. Falla si el usuario tiene solicitudes: la FK es RESTRICT.

    Para esos casos la respuesta correcta es la baja logica, no forzar el borrado.
    """
    usuario = _get_usuario(db, id_usuario)
    cuenta = usuario.cuenta
    db.delete(usuario)
    try:
        db.flush()
        db.delete(cuenta)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="No se puede borrar: el usuario tiene solicitudes o trabajos. Desactivalo en su lugar.",
        )


# ------------------------------------------------------------------ roles


@router.post("/{id_usuario}/cliente", response_model=UsuarioOut, dependencies=[Depends(require_admin)])
def habilitar_cliente(id_usuario: int, db: Session = Depends(get_db)):
    usuario = _get_usuario(db, id_usuario)
    if usuario.cliente is not None:
        raise HTTPException(status_code=409, detail="El usuario ya es cliente")
    db.add(Cliente(id_usuario=id_usuario))
    db.commit()
    db.refresh(usuario)
    return usuario_out(usuario)


@router.delete(
    "/{id_usuario}/cliente", response_model=UsuarioOut, dependencies=[Depends(require_admin)]
)
def quitar_cliente(id_usuario: int, db: Session = Depends(get_db)):
    usuario = _get_usuario(db, id_usuario)
    if usuario.cliente is None:
        raise HTTPException(status_code=404, detail="El usuario no es cliente")
    db.delete(usuario.cliente)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="El cliente tiene solicitudes cargadas")
    db.refresh(usuario)
    return usuario_out(usuario)


@router.post("/{id_usuario}/profesional", response_model=UsuarioOut)
def habilitar_profesional(
    id_usuario: int,
    payload: ProfesionalUpdateIn,
    actual: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    """Un usuario puede darse de alta como profesional por su cuenta."""
    if id_usuario != actual.id_usuario and not actual.cuenta.es_admin:
        raise HTTPException(status_code=403, detail="Solo podes darte de alta a vos mismo")

    usuario = _get_usuario(db, id_usuario)
    if usuario.profesional is not None:
        raise HTTPException(status_code=409, detail="El usuario ya es profesional")

    db.add(
        Profesional(id_usuario=id_usuario, descripcion=payload.descripcion, disponible=True)
    )
    db.commit()
    db.refresh(usuario)
    return usuario_out(usuario)


@router.delete(
    "/{id_usuario}/profesional", response_model=UsuarioOut, dependencies=[Depends(require_admin)]
)
def quitar_profesional(id_usuario: int, db: Session = Depends(get_db)):
    usuario = _get_usuario(db, id_usuario)
    if usuario.profesional is None:
        raise HTTPException(status_code=404, detail="El usuario no es profesional")
    db.delete(usuario.profesional)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="El profesional tiene trabajos en el historial de seguimiento"
        )
    db.refresh(usuario)
    return usuario_out(usuario)
