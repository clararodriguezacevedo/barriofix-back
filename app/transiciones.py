"""Maquina de estados de una solicitud.

El estado NO es una columna de `solicitud`: es la fila de `seguimiento_solicitud`
con `fecha_hasta IS NULL`. Cambiar de estado siempre son dos operaciones (cerrar
la abierta, abrir la nueva) que tienen que ir en la misma transaccion.
"""

from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Estado, SeguimientoSolicitud, Solicitud

PENDIENTE = "PENDIENTE"
ASIGNADO = "ASIGNADO"
EN_PROGRESO = "EN_PROGRESO"
RESUELTO = "RESUELTO"
CANCELADO = "CANCELADO"

# Transiciones permitidas para los endpoints del flujo normal. El endpoint de
# admin las saltea a proposito.
TRANSICIONES = {
    ASIGNADO: {PENDIENTE},
    EN_PROGRESO: {ASIGNADO},
    RESUELTO: {EN_PROGRESO},
    CANCELADO: {PENDIENTE, ASIGNADO, EN_PROGRESO},
    # El profesional se libera y la solicitud vuelve al pool. No es lo mismo
    # que cancelar: la solicitud sigue viva, solo se queda sin profesional.
    PENDIENTE: {ASIGNADO, EN_PROGRESO},
}


def estado_por_nombre(db: Session, nombre: str) -> Estado:
    estado = db.execute(select(Estado).where(Estado.nombre == nombre)).scalar_one_or_none()
    if estado is None:
        raise HTTPException(
            status_code=500,
            detail=f"Falta el estado '{nombre}' en la tabla estado (ver carga inicial)",
        )
    return estado


def estado_inicial(db: Session) -> Estado:
    estado = db.execute(
        select(Estado).where(Estado.es_inicial.is_(True))
    ).scalar_one_or_none()
    if estado is None:
        raise HTTPException(
            status_code=500, detail="No hay ningun estado marcado como es_inicial"
        )
    return estado


def seguimiento_actual(db: Session, id_solicitud: int) -> Optional[SeguimientoSolicitud]:
    """La fila abierta. El indice parcial unico garantiza que hay a lo sumo una."""
    return db.execute(
        select(SeguimientoSolicitud).where(
            SeguimientoSolicitud.id_solicitud == id_solicitud,
            SeguimientoSolicitud.fecha_hasta.is_(None),
        )
    ).scalar_one_or_none()


def lock_solicitud(db: Session, id_solicitud: int) -> Solicitud:
    """Toma el lock de fila ANTES de leer el estado.

    Sin esto, dos profesionales aceptando a la vez leen ambos "PENDIENTE" y el
    segundo se estrella contra el indice unico con un error feo. Con el lock,
    el segundo espera, lee el estado ya actualizado y recibe un 409 limpio.
    """
    solicitud = db.execute(
        select(Solicitud).where(Solicitud.id_solicitud == id_solicitud).with_for_update()
    ).scalar_one_or_none()
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return solicitud


def transicionar(
    db: Session,
    solicitud: Solicitud,
    nombre_destino: str,
    id_usuario_actor: int,
    id_profesional: Optional[int] = None,
    motivo: Optional[str] = None,
    validar: bool = True,
    limpiar_profesional: bool = False,
) -> SeguimientoSolicitud:
    destino = estado_por_nombre(db, nombre_destino)
    actual = seguimiento_actual(db, solicitud.id_solicitud)

    if actual is None:
        raise HTTPException(
            status_code=500,
            detail="La solicitud no tiene estado actual (seguimiento inconsistente)",
        )

    if validar:
        if actual.estado.es_final:
            raise HTTPException(
                status_code=409,
                detail=f"La solicitud ya esta en estado final ({actual.estado.nombre})",
            )
        permitidos = TRANSICIONES.get(nombre_destino, set())
        if actual.estado.nombre not in permitidos:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"No se puede pasar de {actual.estado.nombre} a {nombre_destino}"
                ),
            )

    # clock_timestamp() y no CURRENT_TIMESTAMP: este ultimo devuelve el inicio
    # de la transaccion, asi que al cerrar una fila creada en la misma
    # transaccion fecha_hasta saldria igual a fecha_desde y reventaria el CHECK
    # ck_seguimiento_fechas, que exige estrictamente mayor.
    ahora = db.execute(select(func.clock_timestamp())).scalar_one()

    # Cerrar primero y bajar el cambio a la base: si insertamos la nueva fila
    # antes, quedarian dos abiertas y saltaria el indice parcial unico.
    actual.fecha_hasta = ahora
    db.flush()

    # Si la transicion no trae profesional, se arrastra el de la fila anterior:
    # EN_PROGRESO y RESUELTO siguen siendo del mismo profesional que acepto.
    # `limpiar_profesional` es la excepcion: al volver al pool la solicitud
    # tiene que quedar explicitamente sin profesional, no heredar el anterior.
    if limpiar_profesional:
        profesional_nuevo = None
    elif id_profesional is not None:
        profesional_nuevo = id_profesional
    else:
        profesional_nuevo = actual.id_profesional

    nueva = SeguimientoSolicitud(
        id_solicitud=solicitud.id_solicitud,
        id_estado=destino.id_estado,
        id_profesional=profesional_nuevo,
        id_usuario_actor=id_usuario_actor,
        fecha_desde=ahora,
        motivo=motivo,
    )
    db.add(nueva)
    db.flush()
    return nueva
