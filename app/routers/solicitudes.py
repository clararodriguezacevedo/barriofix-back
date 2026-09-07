"""Solicitudes: ABM y ciclo de vida.

Todas las transiciones toman el lock de la solicitud antes de leer el estado y
cierran/abren la fila de seguimiento en la misma transaccion.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import false, func, or_, select
from sqlalchemy.orm import Session

from app import s3
from app.deps import get_current_profesional, get_current_usuario, get_db, require_admin
from app.models import (
    Categoria,
    Estado,
    Profesional,
    ProfesionalCategoria,
    SeguimientoSolicitud,
    Solicitud,
    Urgencia,
    Usuario,
    Zona,
)
from app.schemas import (
    AceptarIn,
    EstadoForzadoIn,
    SeguimientoOut,
    SolicitudIn,
    SolicitudOut,
    TransicionIn,
)
from app.serializers import seguimiento_out, solicitud_out
from app.transiciones import (
    ASIGNADO,
    CANCELADO,
    EN_PROGRESO,
    PENDIENTE,
    RESUELTO,
    estado_inicial,
    estado_por_nombre,
    lock_solicitud,
    seguimiento_actual,
    transicionar,
)

router = APIRouter(tags=["solicitudes"])


def _validar_catalogos(db: Session, payload: SolicitudIn) -> None:
    """Los catalogos inactivos no se pueden usar en solicitudes nuevas."""
    for modelo, campo, valor, etiqueta in (
        (Categoria, Categoria.id_categoria, payload.id_categoria, "categoria"),
        (Urgencia, Urgencia.id_urgencia, payload.id_urgencia, "urgencia"),
        (Zona, Zona.id_zona, payload.id_zona, "zona"),
    ):
        item = db.execute(select(modelo).where(campo == valor)).scalar_one_or_none()
        if item is None:
            raise HTTPException(status_code=422, detail=f"La {etiqueta} {valor} no existe")
        if not item.activo:
            raise HTTPException(status_code=422, detail=f"La {etiqueta} '{item.nombre}' esta inactiva")


@router.get("/api/solicitudes", response_model=List[SolicitudOut])
def listar_solicitudes(
    estado: Optional[str] = Query(default=None, description="Nombre del estado, ej: PENDIENTE"),
    id_categoria: Optional[int] = None,
    id_zona: Optional[int] = None,
    id_urgencia: Optional[int] = None,
    todas: bool = Query(
        default=False, description="Solo admin: ver las solicitudes de todos los usuarios"
    ),
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    """Por defecto devuelve solo las solicitudes del usuario que consulta.

    Como cliente, las que creo; como profesional, las que tengo asignadas ahora.
    Quien es las dos cosas ve la union. Sin este recorte, cualquier usuario
    autenticado podria leer el nombre, la direccion y el telefono de todos los
    vecinos del barrio.
    """
    stmt = select(Solicitud)

    if id_categoria:
        stmt = stmt.where(Solicitud.id_categoria == id_categoria)
    if id_zona:
        stmt = stmt.where(Solicitud.id_zona == id_zona)
    if id_urgencia:
        stmt = stmt.where(Solicitud.id_urgencia == id_urgencia)

    if todas:
        if not usuario.cuenta.es_admin:
            raise HTTPException(
                status_code=403, detail="Solo un administrador puede ver todas las solicitudes"
            )
    else:
        # Como profesional: las que figuran a mi nombre en la fila abierta del
        # seguimiento. Va como EXISTS y no como JOIN para poder combinarlo con
        # OR con la condicion de cliente.
        asignadas_a_mi = (
            select(SeguimientoSolicitud.id_seguimiento)
            .where(
                SeguimientoSolicitud.id_solicitud == Solicitud.id_solicitud,
                SeguimientoSolicitud.fecha_hasta.is_(None),
                SeguimientoSolicitud.id_profesional == usuario.id_usuario,
            )
            .exists()
        )
        condiciones = []
        if usuario.cliente is not None:
            condiciones.append(Solicitud.id_cliente == usuario.id_usuario)
        if usuario.profesional is not None:
            condiciones.append(asignadas_a_mi)
        stmt = stmt.where(or_(*condiciones) if condiciones else false())

    if estado:
        stmt = stmt.join(
            SeguimientoSolicitud,
            (SeguimientoSolicitud.id_solicitud == Solicitud.id_solicitud)
            & SeguimientoSolicitud.fecha_hasta.is_(None),
        ).join(Estado, Estado.id_estado == SeguimientoSolicitud.id_estado).where(
            Estado.nombre == estado.upper()
        )

    filas = db.execute(stmt.order_by(Solicitud.fecha_creacion.desc())).scalars().all()
    return [solicitud_out(db, s) for s in filas]


@router.get("/api/solicitudes/{id_solicitud}", response_model=SolicitudOut)
def obtener_solicitud(
    id_solicitud: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    solicitud = db.get(Solicitud, id_solicitud)
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    # Un profesional puede mirar una PENDIENTE aunque no sea suya: es el tablero
    # de trabajos disponibles. Cualquier otra tiene que ser propia.
    actual = seguimiento_actual(db, id_solicitud)
    es_mia = solicitud.id_cliente == usuario.id_usuario or (
        actual is not None and actual.id_profesional == usuario.id_usuario
    )
    disponible = (
        usuario.profesional is not None
        and actual is not None
        and actual.estado.nombre == PENDIENTE
    )
    if not (es_mia or disponible or usuario.cuenta.es_admin):
        raise HTTPException(status_code=403, detail="La solicitud es de otro usuario")

    return solicitud_out(db, solicitud)


@router.post("/api/solicitudes", response_model=SolicitudOut, status_code=201)
def crear_solicitud(
    payload: SolicitudIn,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    """Crea la solicitud y su primera fila de seguimiento en una transaccion.

    Una solicitud sin fila de seguimiento no tendria estado y romperia todas
    las consultas, asi que las dos cosas entran juntas o no entra ninguna.
    """
    if usuario.cliente is None:
        raise HTTPException(status_code=403, detail="Solo un cliente puede crear solicitudes")

    _validar_catalogos(db, payload)

    solicitud = Solicitud(
        id_cliente=usuario.id_usuario,
        id_categoria=payload.id_categoria,
        id_urgencia=payload.id_urgencia,
        id_zona=payload.id_zona,
        titulo=payload.titulo,
        descripcion=payload.descripcion,
        direccion=payload.direccion,
    )
    db.add(solicitud)
    db.flush()

    db.add(
        SeguimientoSolicitud(
            id_solicitud=solicitud.id_solicitud,
            id_estado=estado_inicial(db).id_estado,
            id_usuario_actor=usuario.id_usuario,
        )
    )

    db.commit()
    db.refresh(solicitud)
    return solicitud_out(db, solicitud)


@router.put("/api/solicitudes/{id_solicitud}", response_model=SolicitudOut)
def actualizar_solicitud(
    id_solicitud: int,
    payload: SolicitudIn,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    """Editar solo mientras nadie la tomo.

    Una vez que un profesional acepto, cambiarle el trabajo abajo de los pies
    seria cambiar el acuerdo despues de cerrado.
    """
    solicitud = db.get(Solicitud, id_solicitud)
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if solicitud.id_cliente != usuario.id_usuario and not usuario.cuenta.es_admin:
        raise HTTPException(status_code=403, detail="La solicitud es de otro cliente")

    actual = seguimiento_actual(db, id_solicitud)
    if actual is not None and actual.estado.nombre != PENDIENTE and not usuario.cuenta.es_admin:
        raise HTTPException(
            status_code=409,
            detail=f"Solo se puede editar mientras esta PENDIENTE (ahora esta {actual.estado.nombre})",
        )

    _validar_catalogos(db, payload)

    for campo, valor in payload.model_dump().items():
        setattr(solicitud, campo, valor)

    db.commit()
    db.refresh(solicitud)
    return solicitud_out(db, solicitud)


@router.delete("/api/solicitudes/{id_solicitud}", status_code=204, dependencies=[Depends(require_admin)])
def borrar_solicitud(id_solicitud: int, db: Session = Depends(get_db)):
    """Borrado real (solo admin). El usuario normal cancela, no borra.

    Las filas de foto_solicitud se van en cascada, pero los objetos de S3 no:
    hay que borrarlos primero o quedan huerfanos.
    """
    solicitud = db.get(Solicitud, id_solicitud)
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    s3.borrar_varios([f.s3_key for f in solicitud.fotos])
    db.delete(solicitud)
    db.commit()


# ------------------------------------------------------------- seguimiento


@router.get("/api/solicitudes/{id_solicitud}/seguimiento", response_model=List[SeguimientoOut])
def historial(
    id_solicitud: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    if db.get(Solicitud, id_solicitud) is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    filas = db.execute(
        select(SeguimientoSolicitud)
        .where(SeguimientoSolicitud.id_solicitud == id_solicitud)
        .order_by(SeguimientoSolicitud.fecha_desde)
    ).scalars().all()
    return [seguimiento_out(f) for f in filas]


@router.post("/api/solicitudes/{id_solicitud}/aceptar", response_model=SolicitudOut)
def aceptar(
    id_solicitud: int,
    payload: AceptarIn,
    profesional: Profesional = Depends(get_current_profesional),
    db: Session = Depends(get_db),
):
    """PENDIENTE -> ASIGNADO.

    El lock hace que dos profesionales simultaneos se serialicen: el segundo
    lee el estado ya cambiado y recibe 409 en vez de estrellarse contra el
    indice unico.
    """
    solicitud = lock_solicitud(db, id_solicitud)
    transicionar(
        db,
        solicitud,
        ASIGNADO,
        id_usuario_actor=profesional.id_usuario,
        id_profesional=profesional.id_usuario,
        motivo=payload.motivo,
    )
    db.commit()
    db.refresh(solicitud)
    return solicitud_out(db, solicitud)


def _transicion_del_profesional(
    db: Session, id_solicitud: int, destino: str, profesional: Profesional, motivo: Optional[str]
) -> Solicitud:
    solicitud = lock_solicitud(db, id_solicitud)
    actual = seguimiento_actual(db, id_solicitud)
    if actual is not None and actual.id_profesional != profesional.id_usuario:
        raise HTTPException(status_code=403, detail="La solicitud esta asignada a otro profesional")
    transicionar(db, solicitud, destino, id_usuario_actor=profesional.id_usuario, motivo=motivo)
    db.commit()
    db.refresh(solicitud)
    return solicitud


@router.post("/api/solicitudes/{id_solicitud}/iniciar", response_model=SolicitudOut)
def iniciar(
    id_solicitud: int,
    payload: TransicionIn,
    profesional: Profesional = Depends(get_current_profesional),
    db: Session = Depends(get_db),
):
    """ASIGNADO -> EN_PROGRESO."""
    solicitud = _transicion_del_profesional(db, id_solicitud, EN_PROGRESO, profesional, payload.motivo)
    return solicitud_out(db, solicitud)


@router.post("/api/solicitudes/{id_solicitud}/resolver", response_model=SolicitudOut)
def resolver(
    id_solicitud: int,
    payload: TransicionIn,
    profesional: Profesional = Depends(get_current_profesional),
    db: Session = Depends(get_db),
):
    """EN_PROGRESO -> RESUELTO. Habilita la calificacion."""
    solicitud = _transicion_del_profesional(db, id_solicitud, RESUELTO, profesional, payload.motivo)
    return solicitud_out(db, solicitud)


@router.post("/api/solicitudes/{id_solicitud}/liberar", response_model=SolicitudOut)
def liberar(
    id_solicitud: int,
    payload: TransicionIn,
    profesional: Profesional = Depends(get_current_profesional),
    db: Session = Depends(get_db),
):
    """ASIGNADO o EN_PROGRESO -> PENDIENTE: el profesional devuelve el trabajo.

    No es lo mismo que cancelar. La solicitud sigue viva y vuelve al tablero
    para que la tome otro; el que se baja es el profesional. Queda registrado
    en el historial con su motivo.
    """
    solicitud = lock_solicitud(db, id_solicitud)
    actual = seguimiento_actual(db, id_solicitud)
    if actual is not None and actual.id_profesional != profesional.id_usuario:
        raise HTTPException(status_code=403, detail="La solicitud esta asignada a otro profesional")

    transicionar(
        db,
        solicitud,
        PENDIENTE,
        id_usuario_actor=profesional.id_usuario,
        motivo=payload.motivo,
        limpiar_profesional=True,
    )
    db.commit()
    db.refresh(solicitud)
    return solicitud_out(db, solicitud)


@router.post("/api/solicitudes/{id_solicitud}/cancelar", response_model=SolicitudOut)
def cancelar(
    id_solicitud: int,
    payload: TransicionIn,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    """Cancelacion por el cliente.

    Toca dos tablas: la transicion a CANCELADO y las dos columnas de solicitud.
    El CHECK ck_solicitud_cancelacion exige que el flag y la fecha vayan
    siempre juntos, asi que van en la misma transaccion.
    """
    solicitud = lock_solicitud(db, id_solicitud)
    if solicitud.id_cliente != usuario.id_usuario and not usuario.cuenta.es_admin:
        raise HTTPException(status_code=403, detail="La solicitud es de otro cliente")

    nueva = transicionar(
        db, solicitud, CANCELADO, id_usuario_actor=usuario.id_usuario, motivo=payload.motivo
    )
    solicitud.cancelada_por_cliente = True
    solicitud.fecha_cancelacion_cliente = nueva.fecha_desde

    db.commit()
    db.refresh(solicitud)
    return solicitud_out(db, solicitud)


@router.post(
    "/api/solicitudes/{id_solicitud}/estado",
    response_model=SolicitudOut,
    dependencies=[Depends(require_admin)],
)
def forzar_estado(
    id_solicitud: int,
    payload: EstadoForzadoIn,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    """Transicion arbitraria para arreglar datos a mano (solo admin).

    Saltea las reglas de la maquina de estados, pero NO el indice parcial
    unico: sigue siendo imposible dejar dos filas abiertas.
    """
    solicitud = lock_solicitud(db, id_solicitud)
    destino = db.get(Estado, payload.id_estado)
    if destino is None:
        raise HTTPException(status_code=404, detail="Estado no encontrado")

    transicionar(
        db,
        solicitud,
        destino.nombre,
        id_usuario_actor=usuario.id_usuario,
        id_profesional=payload.id_profesional,
        motivo=payload.motivo,
        validar=False,
    )
    db.commit()
    db.refresh(solicitud)
    return solicitud_out(db, solicitud)


# ------------------------------------------------------------- trabajos


@router.get("/api/trabajos", response_model=List[SolicitudOut])
def trabajos_disponibles(
    id_zona: Optional[int] = None,
    id_urgencia: Optional[int] = None,
    todas_las_categorias: bool = Query(
        default=False, description="Ignorar el filtro por mis especialidades"
    ),
    profesional: Profesional = Depends(get_current_profesional),
    db: Session = Depends(get_db),
):
    """Solicitudes PENDIENTE que este profesional puede tomar.

    Por defecto se filtran por sus especialidades: no tiene sentido ofrecerle
    un trabajo de plomeria a un electricista.
    """
    stmt = (
        select(Solicitud)
        .join(
            SeguimientoSolicitud,
            (SeguimientoSolicitud.id_solicitud == Solicitud.id_solicitud)
            & SeguimientoSolicitud.fecha_hasta.is_(None),
        )
        .join(Estado, Estado.id_estado == SeguimientoSolicitud.id_estado)
        .where(Estado.nombre == PENDIENTE)
    )

    if not todas_las_categorias:
        mis_categorias = select(ProfesionalCategoria.id_categoria).where(
            ProfesionalCategoria.id_profesional == profesional.id_usuario
        )
        stmt = stmt.where(Solicitud.id_categoria.in_(mis_categorias))

    if id_zona:
        stmt = stmt.where(Solicitud.id_zona == id_zona)
    if id_urgencia:
        stmt = stmt.where(Solicitud.id_urgencia == id_urgencia)

    filas = (
        db.execute(stmt.order_by(Solicitud.fecha_creacion.desc())).scalars().all()
    )
    return [solicitud_out(db, s) for s in filas]
