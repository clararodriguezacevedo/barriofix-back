"""Profesionales y sus especialidades (N:M con categoria)."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import get_current_profesional, get_current_usuario, get_db
from app.models import Categoria, Profesional, ProfesionalCategoria, Usuario
from app.schemas import (
    CalificacionOut,
    CategoriaOut,
    CategoriasIn,
    DisponibleIn,
    ProfesionalOut,
    ProfesionalUpdateIn,
)
from app.serializers import profesional_out

router = APIRouter(prefix="/api/profesionales", tags=["profesionales"])


def _get_profesional(db: Session, id_usuario: int) -> Profesional:
    profesional = db.get(Profesional, id_usuario)
    if profesional is None:
        raise HTTPException(status_code=404, detail="Profesional no encontrado")
    return profesional


def _es_uno_mismo_o_admin(profesional: Profesional, usuario: Usuario) -> None:
    if profesional.id_usuario != usuario.id_usuario and not usuario.cuenta.es_admin:
        raise HTTPException(status_code=403, detail="Solo podes editar tu propio perfil")


@router.get("", response_model=List[ProfesionalOut])
def listar(
    id_categoria: Optional[int] = None,
    disponible: Optional[bool] = None,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    stmt = select(Profesional)
    if disponible is not None:
        stmt = stmt.where(Profesional.disponible.is_(disponible))
    if id_categoria:
        stmt = stmt.join(
            ProfesionalCategoria,
            ProfesionalCategoria.id_profesional == Profesional.id_usuario,
        ).where(ProfesionalCategoria.id_categoria == id_categoria)

    return [profesional_out(db, p) for p in db.execute(stmt).scalars().all()]


@router.get("/{id_usuario}", response_model=ProfesionalOut)
def obtener(
    id_usuario: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    return profesional_out(db, _get_profesional(db, id_usuario))


@router.put("/{id_usuario}", response_model=ProfesionalOut)
def actualizar(
    id_usuario: int,
    payload: ProfesionalUpdateIn,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    profesional = _get_profesional(db, id_usuario)
    _es_uno_mismo_o_admin(profesional, usuario)
    profesional.descripcion = payload.descripcion
    db.commit()
    db.refresh(profesional)
    return profesional_out(db, profesional)


@router.patch("/{id_usuario}/disponible", response_model=ProfesionalOut)
def cambiar_disponible(
    id_usuario: int,
    payload: DisponibleIn,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    """No afecta a los trabajos ya asignados: solo deja de aparecer en las
    busquedas de profesionales disponibles."""
    profesional = _get_profesional(db, id_usuario)
    _es_uno_mismo_o_admin(profesional, usuario)
    profesional.disponible = payload.disponible
    db.commit()
    db.refresh(profesional)
    return profesional_out(db, profesional)


# ------------------------------------------------------- especialidades


@router.get("/{id_usuario}/categorias", response_model=List[CategoriaOut])
def listar_categorias(
    id_usuario: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    return _get_profesional(db, id_usuario).categorias


@router.put("/{id_usuario}/categorias", response_model=List[CategoriaOut])
def reemplazar_categorias(
    id_usuario: int,
    payload: CategoriasIn,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    """Reemplaza el set completo en una transaccion.

    Es lo que necesita una pantalla de perfil con checkboxes: una sola llamada
    y sin estados intermedios raros si el usuario tilda y destilda varias.
    """
    profesional = _get_profesional(db, id_usuario)
    _es_uno_mismo_o_admin(profesional, usuario)

    pedidas = set(payload.categorias)
    if pedidas:
        existentes = set(
            db.execute(
                select(Categoria.id_categoria).where(Categoria.id_categoria.in_(pedidas))
            ).scalars().all()
        )
        faltantes = pedidas - existentes
        if faltantes:
            raise HTTPException(
                status_code=422, detail=f"Categorias inexistentes: {sorted(faltantes)}"
            )

    actuales = set(
        db.execute(
            select(ProfesionalCategoria.id_categoria).where(
                ProfesionalCategoria.id_profesional == id_usuario
            )
        ).scalars().all()
    )

    for id_categoria in actuales - pedidas:
        db.delete(db.get(ProfesionalCategoria, (id_usuario, id_categoria)))
    for id_categoria in pedidas - actuales:
        db.add(ProfesionalCategoria(id_profesional=id_usuario, id_categoria=id_categoria))

    db.commit()
    db.refresh(profesional)
    return profesional.categorias


@router.post("/{id_usuario}/categorias/{id_categoria}", response_model=List[CategoriaOut], status_code=201)
def agregar_categoria(
    id_usuario: int,
    id_categoria: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    profesional = _get_profesional(db, id_usuario)
    _es_uno_mismo_o_admin(profesional, usuario)
    if db.get(Categoria, id_categoria) is None:
        raise HTTPException(status_code=404, detail="Categoria no encontrada")

    db.add(ProfesionalCategoria(id_profesional=id_usuario, id_categoria=id_categoria))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="El profesional ya tiene esa especialidad")
    db.refresh(profesional)
    return profesional.categorias


@router.delete("/{id_usuario}/categorias/{id_categoria}", response_model=List[CategoriaOut])
def quitar_categoria(
    id_usuario: int,
    id_categoria: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    profesional = _get_profesional(db, id_usuario)
    _es_uno_mismo_o_admin(profesional, usuario)

    fila = db.get(ProfesionalCategoria, (id_usuario, id_categoria))
    if fila is None:
        raise HTTPException(status_code=404, detail="El profesional no tiene esa especialidad")
    db.delete(fila)
    db.commit()
    db.refresh(profesional)
    return profesional.categorias
