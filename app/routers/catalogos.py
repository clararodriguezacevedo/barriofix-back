"""ABM de los catalogos: categoria, zona, urgencia y estado.

Los tres primeros comparten exactamente la misma forma, asi que se generan con
una factory en vez de repetir el mismo CRUD tres veces. `estado` va aparte
porque tiene reglas propias (es_inicial unico, es_final excluyente).

Lectura: publica. Escritura: solo admin.
"""

from typing import Optional, Type

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import get_db, require_admin
from app.models import Categoria, Estado, Urgencia, Zona
from app.schemas import (
    ActivoIn,
    CategoriaIn,
    CategoriaOut,
    EstadoIn,
    EstadoOut,
    UrgenciaIn,
    UrgenciaOut,
    ZonaIn,
    ZonaOut,
)

router = APIRouter(tags=["catalogos"])


def _registrar_catalogo(
    prefix: str,
    modelo: Type,
    pk: str,
    schema_out,
    schema_in,
    orden,
    etiqueta: str,
):
    @router.get(prefix, response_model=list[schema_out], name=f"listar_{etiqueta}")
    def listar(activo: Optional[bool] = True, db: Session = Depends(get_db)):
        stmt = select(modelo)
        if activo is not None:
            stmt = stmt.where(modelo.activo.is_(activo))
        return db.execute(stmt.order_by(orden)).scalars().all()

    @router.get(prefix + "/{item_id}", response_model=schema_out, name=f"obtener_{etiqueta}")
    def obtener(item_id: int, db: Session = Depends(get_db)):
        item = db.get(modelo, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail=f"{etiqueta} no encontrada")
        return item

    @router.post(
        prefix,
        response_model=schema_out,
        status_code=201,
        dependencies=[Depends(require_admin)],
        name=f"crear_{etiqueta}",
    )
    def crear(payload: schema_in, db: Session = Depends(get_db)):
        item = modelo(**payload.model_dump())
        db.add(item)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail=f"Ya existe una {etiqueta} con esos datos")
        db.refresh(item)
        return item

    @router.put(
        prefix + "/{item_id}",
        response_model=schema_out,
        dependencies=[Depends(require_admin)],
        name=f"actualizar_{etiqueta}",
    )
    def actualizar(item_id: int, payload: schema_in, db: Session = Depends(get_db)):
        item = db.get(modelo, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail=f"{etiqueta} no encontrada")
        for campo, valor in payload.model_dump().items():
            setattr(item, campo, valor)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail=f"Ya existe una {etiqueta} con esos datos")
        db.refresh(item)
        return item

    @router.patch(
        prefix + "/{item_id}/activo",
        response_model=schema_out,
        dependencies=[Depends(require_admin)],
        name=f"activar_{etiqueta}",
    )
    def cambiar_activo(item_id: int, payload: ActivoIn, db: Session = Depends(get_db)):
        """Baja logica: es la forma normal de sacar de circulacion un catalogo,
        porque el DELETE real choca contra las FK de las solicitudes que lo usan."""
        item = db.get(modelo, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail=f"{etiqueta} no encontrada")
        item.activo = payload.activo
        db.commit()
        db.refresh(item)
        return item

    @router.delete(
        prefix + "/{item_id}",
        status_code=204,
        dependencies=[Depends(require_admin)],
        name=f"borrar_{etiqueta}",
    )
    def borrar(item_id: int, db: Session = Depends(get_db)):
        item = db.get(modelo, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail=f"{etiqueta} no encontrada")
        db.delete(item)
        try:
            db.commit()
        except IntegrityError:
            # FK ON DELETE RESTRICT: hay solicitudes que la referencian. Dejamos
            # que la base sea la autoridad en vez de replicar el chequeo aca.
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail=f"No se puede borrar: hay registros que usan esta {etiqueta}. Desactivala en su lugar.",
            )


_registrar_catalogo(
    "/api/categorias", Categoria, "id_categoria", CategoriaOut, CategoriaIn, Categoria.nombre, "categoria"
)
_registrar_catalogo("/api/zonas", Zona, "id_zona", ZonaOut, ZonaIn, Zona.nombre, "zona")
_registrar_catalogo(
    "/api/urgencias",
    Urgencia,
    "id_urgencia",
    UrgenciaOut,
    UrgenciaIn,
    Urgencia.orden_prioridad,
    "urgencia",
)


# ------------------------------------------------------------------ estado
# Va aparte: de estas 5 filas depende todo el ciclo de vida de la aplicacion.


@router.get("/api/estados", response_model=list[EstadoOut], tags=["catalogos"])
def listar_estados(db: Session = Depends(get_db)):
    return db.execute(select(Estado).order_by(Estado.id_estado)).scalars().all()


def _validar_estado(payload: EstadoIn) -> None:
    if payload.es_inicial and payload.es_final:
        raise HTTPException(
            status_code=422, detail="Un estado no puede ser inicial y final a la vez"
        )


def _liberar_inicial(db: Session, excepto_id: Optional[int] = None) -> None:
    """Solo puede haber un estado inicial (indice parcial unico en la base).

    Desmarcamos el anterior en la misma transaccion, si no el INSERT/UPDATE
    falla contra el indice.
    """
    stmt = select(Estado).where(Estado.es_inicial.is_(True))
    if excepto_id is not None:
        stmt = stmt.where(Estado.id_estado != excepto_id)
    for previo in db.execute(stmt).scalars().all():
        previo.es_inicial = False
    db.flush()


@router.post(
    "/api/estados", response_model=EstadoOut, status_code=201, dependencies=[Depends(require_admin)]
)
def crear_estado(payload: EstadoIn, db: Session = Depends(get_db)):
    _validar_estado(payload)
    if payload.es_inicial:
        _liberar_inicial(db)
    estado = Estado(**payload.model_dump())
    db.add(estado)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ya existe un estado con ese nombre")
    db.refresh(estado)
    return estado


@router.put(
    "/api/estados/{estado_id}", response_model=EstadoOut, dependencies=[Depends(require_admin)]
)
def actualizar_estado(estado_id: int, payload: EstadoIn, db: Session = Depends(get_db)):
    _validar_estado(payload)
    estado = db.get(Estado, estado_id)
    if estado is None:
        raise HTTPException(status_code=404, detail="Estado no encontrado")
    if payload.es_inicial:
        _liberar_inicial(db, excepto_id=estado_id)
    for campo, valor in payload.model_dump().items():
        setattr(estado, campo, valor)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ya existe un estado con ese nombre")
    db.refresh(estado)
    return estado


@router.delete("/api/estados/{estado_id}", status_code=204, dependencies=[Depends(require_admin)])
def borrar_estado(estado_id: int, db: Session = Depends(get_db)):
    estado = db.get(Estado, estado_id)
    if estado is None:
        raise HTTPException(status_code=404, detail="Estado no encontrado")
    db.delete(estado)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="No se puede borrar: hay seguimientos que referencian este estado",
        )
