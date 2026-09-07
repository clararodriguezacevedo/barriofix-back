"""Calificacion de un trabajo terminado.

`calificacion` no guarda id_cliente ni id_profesional: ambos se derivan de
solicitud y del historial de seguimiento.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import get_current_usuario, get_db, require_admin
from app.models import Calificacion, Estado, SeguimientoSolicitud, Solicitud, Usuario
from app.schemas import CalificacionIn, CalificacionOut
from app.transiciones import RESUELTO, seguimiento_actual

router = APIRouter(tags=["calificaciones"])


@router.get("/api/solicitudes/{id_solicitud}/calificacion", response_model=CalificacionOut)
def obtener(
    id_solicitud: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    calificacion = db.execute(
        select(Calificacion).where(Calificacion.id_solicitud == id_solicitud)
    ).scalar_one_or_none()
    if calificacion is None:
        raise HTTPException(status_code=404, detail="La solicitud todavia no fue calificada")
    return calificacion


@router.post(
    "/api/solicitudes/{id_solicitud}/calificacion", response_model=CalificacionOut, status_code=201
)
def calificar(
    id_solicitud: int,
    payload: CalificacionIn,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    """Solo el cliente dueño, solo si el trabajo esta RESUELTO, y una sola vez."""
    solicitud = db.get(Solicitud, id_solicitud)
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if solicitud.id_cliente != usuario.id_usuario and not usuario.cuenta.es_admin:
        raise HTTPException(status_code=403, detail="Solo el cliente puede calificar su solicitud")

    actual = seguimiento_actual(db, id_solicitud)
    if actual is None or actual.estado.nombre != RESUELTO:
        estado_actual = actual.estado.nombre if actual else "desconocido"
        raise HTTPException(
            status_code=409,
            detail=f"Solo se puede calificar un trabajo RESUELTO (esta {estado_actual})",
        )

    calificacion = Calificacion(
        id_solicitud=id_solicitud,
        puntuacion=payload.puntuacion,
        comentario=payload.comentario,
    )
    db.add(calificacion)
    try:
        db.commit()
    except IntegrityError:
        # uq_calificacion_solicitud: una solicitud se califica una sola vez.
        db.rollback()
        raise HTTPException(status_code=409, detail="La solicitud ya fue calificada")

    db.refresh(calificacion)
    return calificacion


@router.put("/api/calificaciones/{id_calificacion}", response_model=CalificacionOut)
def editar(
    id_calificacion: int,
    payload: CalificacionIn,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    calificacion = db.get(Calificacion, id_calificacion)
    if calificacion is None:
        raise HTTPException(status_code=404, detail="Calificacion no encontrada")
    if calificacion.solicitud.id_cliente != usuario.id_usuario and not usuario.cuenta.es_admin:
        raise HTTPException(status_code=403, detail="La calificacion es de otro cliente")

    calificacion.puntuacion = payload.puntuacion
    calificacion.comentario = payload.comentario
    db.commit()
    db.refresh(calificacion)
    return calificacion


@router.delete(
    "/api/calificaciones/{id_calificacion}", status_code=204, dependencies=[Depends(require_admin)]
)
def borrar(id_calificacion: int, db: Session = Depends(get_db)):
    """Moderacion: sacar un comentario abusivo."""
    calificacion = db.get(Calificacion, id_calificacion)
    if calificacion is None:
        raise HTTPException(status_code=404, detail="Calificacion no encontrada")
    db.delete(calificacion)
    db.commit()


@router.get(
    "/api/profesionales/{id_profesional}/calificaciones", response_model=List[CalificacionOut]
)
def del_profesional(
    id_profesional: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    """Todas las calificaciones de un profesional.

    Hay que llegar por seguimiento: la calificacion solo conoce la solicitud.
    """
    trabajos = (
        select(SeguimientoSolicitud.id_solicitud)
        .join(Estado, Estado.id_estado == SeguimientoSolicitud.id_estado)
        .where(
            SeguimientoSolicitud.id_profesional == id_profesional,
            SeguimientoSolicitud.fecha_hasta.is_(None),
            Estado.nombre == RESUELTO,
        )
    )
    return db.execute(
        select(Calificacion)
        .where(Calificacion.id_solicitud.in_(trabajos))
        .order_by(Calificacion.fecha_calificacion.desc())
    ).scalars().all()
