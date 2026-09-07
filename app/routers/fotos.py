"""Fotos de una solicitud: metadata en RDS, archivo en S3."""

from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import s3
from app.deps import get_current_usuario, get_db
from app.models import FotoSolicitud, Solicitud, Usuario
from app.schemas import FotoOut, FotoUpdateIn
from app.serializers import foto_out
from app.transiciones import seguimiento_actual

router = APIRouter(tags=["fotos"])

# Valores que admite el CHECK ck_foto_tipo. OTRA queda reservado para un caso
# de uso futuro: hoy ningun endpoint lo asigna.
TIPOS_VALIDOS = {"ANTES", "DESPUES", "OTRA"}
MAX_BYTES = 10 * 1024 * 1024


@router.get("/api/solicitudes/{id_solicitud}/fotos", response_model=List[FotoOut])
def listar_fotos(
    id_solicitud: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    if db.get(Solicitud, id_solicitud) is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    filas = db.execute(
        select(FotoSolicitud)
        .where(FotoSolicitud.id_solicitud == id_solicitud)
        .order_by(FotoSolicitud.fecha_subida)
    ).scalars().all()
    return [foto_out(f) for f in filas]


@router.post("/api/solicitudes/{id_solicitud}/fotos", response_model=FotoOut, status_code=201)
async def subir_foto(
    id_solicitud: int,
    archivo: UploadFile = File(...),
    descripcion: str = Form(default=""),
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    """Sube a S3 y despues inserta la fila.

    En ese orden a proposito: si falla el INSERT borramos el objeto y no queda
    nada; al reves quedaria una fila apuntando a un archivo que no existe, que
    es mucho peor porque la app la muestra y rompe al descargarla.

    El tipo de foto NO lo elige quien sube: lo determina el rol. El cliente
    documenta el problema (ANTES), el profesional el trabajo terminado
    (DESPUES). Dejarlo a eleccion permitia que el mismo archivo se clasificara
    distinto segun quien lo cargara.
    """
    solicitud = db.get(Solicitud, id_solicitud)
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    actual = seguimiento_actual(db, id_solicitud)

    if solicitud.id_cliente == usuario.id_usuario:
        tipo = "ANTES"
    elif actual is not None and actual.id_profesional == usuario.id_usuario:
        tipo = "DESPUES"
    else:
        raise HTTPException(
            status_code=403,
            detail="Solo el cliente de la solicitud o el profesional asignado pueden subir fotos",
        )

    contenido = await archivo.read()
    if len(contenido) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="El archivo supera los 10 MB")
    if not contenido:
        raise HTTPException(status_code=422, detail="El archivo esta vacio")

    key = s3.build_key(id_solicitud, archivo.filename or "foto")
    s3.subir(key, contenido, archivo.content_type or "application/octet-stream")

    foto = FotoSolicitud(
        id_solicitud=id_solicitud,
        id_usuario_carga=usuario.id_usuario,
        tipo_foto=tipo,
        s3_key=key,
        nombre_archivo=archivo.filename or "foto",
        descripcion=descripcion or None,
    )
    db.add(foto)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        s3.borrar(key)
        raise HTTPException(status_code=409, detail="No se pudo registrar la foto")

    db.refresh(foto)
    return foto_out(foto)


@router.get("/api/fotos/{id_foto}/contenido")
def descargar_foto(
    id_foto: int,
    db: Session = Depends(get_db),
):
    """Devuelve el binario. Sin autenticacion para poder usarlo en un <img src>:
    el browser no manda el header Authorization en las etiquetas img."""
    foto = db.get(FotoSolicitud, id_foto)
    if foto is None:
        raise HTTPException(status_code=404, detail="Foto no encontrada")

    obj = s3.descargar(foto.s3_key)
    return StreamingResponse(
        obj["Body"].iter_chunks(),
        media_type=obj.get("ContentType", "application/octet-stream"),
    )


@router.patch("/api/fotos/{id_foto}", response_model=FotoOut)
def actualizar_foto(
    id_foto: int,
    payload: FotoUpdateIn,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    """Solo la descripcion.

    s3_key no se edita porque es UNIQUE y apunta al objeto real, y tipo_foto
    tampoco: lo determina el rol de quien subio la foto, no una eleccion.
    """
    foto = db.get(FotoSolicitud, id_foto)
    if foto is None:
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    if foto.id_usuario_carga != usuario.id_usuario and not usuario.cuenta.es_admin:
        raise HTTPException(status_code=403, detail="La foto la subio otro usuario")

    if payload.descripcion is not None:
        foto.descripcion = payload.descripcion

    db.commit()
    db.refresh(foto)
    return foto_out(foto)


@router.delete("/api/fotos/{id_foto}", status_code=204)
def borrar_foto(
    id_foto: int,
    usuario: Usuario = Depends(get_current_usuario),
    db: Session = Depends(get_db),
):
    """Borra la fila y el objeto. Si solo borraramos la fila, el archivo
    quedaria en el bucket para siempre sin que nada lo referencie."""
    foto = db.get(FotoSolicitud, id_foto)
    if foto is None:
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    if foto.id_usuario_carga != usuario.id_usuario and not usuario.cuenta.es_admin:
        raise HTTPException(status_code=403, detail="La foto la subio otro usuario")

    key = foto.s3_key
    db.delete(foto)
    db.commit()
    s3.borrar(key)
