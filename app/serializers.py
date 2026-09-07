"""Armado de las respuestas.

Estado y profesional de una solicitud no son columnas: salen de la fila abierta
de seguimiento. Centralizar eso aca evita que cada router lo resuelva distinto.
"""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Calificacion,
    Estado,
    FotoSolicitud,
    Profesional,
    SeguimientoSolicitud,
    Solicitud,
    Usuario,
)
from app.transiciones import RESUELTO, seguimiento_actual


def usuario_breve(usuario: Optional[Usuario]) -> Optional[dict]:
    if usuario is None:
        return None
    return {
        "id_usuario": usuario.id_usuario,
        "nombre": usuario.nombre,
        "apellido": usuario.apellido,
    }


def foto_out(foto: FotoSolicitud) -> dict:
    return {
        "id_foto": foto.id_foto,
        "id_solicitud": foto.id_solicitud,
        "tipo_foto": foto.tipo_foto,
        "s3_key": foto.s3_key,
        "nombre_archivo": foto.nombre_archivo,
        "fecha_subida": foto.fecha_subida,
        "descripcion": foto.descripcion,
        "url": f"/api/fotos/{foto.id_foto}/contenido",
    }


def seguimiento_out(fila: SeguimientoSolicitud) -> dict:
    return {
        "id_seguimiento": fila.id_seguimiento,
        "estado": fila.estado,
        "profesional": usuario_breve(fila.profesional.usuario) if fila.profesional else None,
        "actor": usuario_breve(fila.actor),
        "fecha_desde": fila.fecha_desde,
        "fecha_hasta": fila.fecha_hasta,
        "motivo": fila.motivo,
    }


def solicitud_out(db: Session, solicitud: Solicitud) -> dict:
    actual = seguimiento_actual(db, solicitud.id_solicitud)
    if actual is None:
        # No deberia pasar: se crea junto con la solicitud en la misma
        # transaccion. Si pasa, es un dato corrupto y conviene que se note.
        raise ValueError(
            f"La solicitud {solicitud.id_solicitud} no tiene fila de seguimiento abierta"
        )

    return {
        "id_solicitud": solicitud.id_solicitud,
        "titulo": solicitud.titulo,
        "descripcion": solicitud.descripcion,
        "direccion": solicitud.direccion,
        "fecha_creacion": solicitud.fecha_creacion,
        "cancelada_por_cliente": solicitud.cancelada_por_cliente,
        "fecha_cancelacion_cliente": solicitud.fecha_cancelacion_cliente,
        "categoria": solicitud.categoria,
        "urgencia": solicitud.urgencia,
        "zona": solicitud.zona,
        "cliente": usuario_breve(solicitud.cliente.usuario),
        "estado": actual.estado,
        "profesional": usuario_breve(actual.profesional.usuario) if actual.profesional else None,
        "calificacion": solicitud.calificacion,
        "fotos": [foto_out(f) for f in solicitud.fotos],
    }


def profesional_out(db: Session, profesional: Profesional) -> dict:
    """Ficha del profesional con sus metricas.

    El promedio y el conteo salen de calificacion -> solicitud -> seguimiento:
    calificacion no guarda id_profesional, hay que llegar por el historial.
    """
    trabajos = (
        select(SeguimientoSolicitud.id_solicitud)
        .join(Estado, Estado.id_estado == SeguimientoSolicitud.id_estado)
        .where(
            SeguimientoSolicitud.id_profesional == profesional.id_usuario,
            SeguimientoSolicitud.fecha_hasta.is_(None),
            Estado.nombre == RESUELTO,
        )
        .subquery()
    )

    promedio = db.execute(
        select(func.avg(Calificacion.puntuacion)).where(
            Calificacion.id_solicitud.in_(select(trabajos.c.id_solicitud))
        )
    ).scalar()

    resueltos = db.execute(
        select(func.count()).select_from(trabajos)
    ).scalar_one()

    return {
        "id_usuario": profesional.id_usuario,
        "nombre": profesional.usuario.nombre,
        "apellido": profesional.usuario.apellido,
        "email": profesional.usuario.email,
        "telefono": profesional.usuario.telefono,
        "descripcion": profesional.descripcion,
        "disponible": profesional.disponible,
        "categorias": profesional.categorias,
        "calificacion_promedio": round(float(promedio), 2) if promedio is not None else None,
        "trabajos_resueltos": resueltos,
    }
