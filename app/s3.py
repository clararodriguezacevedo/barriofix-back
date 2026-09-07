"""Acceso al bucket de fotos.

Las credenciales salen del rol IAM de la instancia (LabInstanceProfile) via el
servicio de metadata. Desde las subredes privadas el trafico a S3 sale por el
Gateway VPC Endpoint, no por internet.
"""

import os
import uuid
from typing import Iterable

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
MEDIA_BUCKET = os.environ.get("MEDIA_BUCKET", "barriofix-media-clara")

s3 = boto3.client("s3", region_name=AWS_REGION)


def build_key(id_solicitud: int, nombre_archivo: str) -> str:
    """Key unica por archivo.

    s3_key es UNIQUE en la base, asi que no puede derivarse del nombre original:
    dos vecinos subiendo 'foto.jpg' chocarian.
    """
    limpio = os.path.basename(nombre_archivo).replace("/", "_")
    return f"solicitudes/{id_solicitud}/{uuid.uuid4().hex}-{limpio}"


def subir(key: str, contenido: bytes, content_type: str) -> None:
    try:
        s3.put_object(Bucket=MEDIA_BUCKET, Key=key, Body=contenido, ContentType=content_type)
    except (ClientError, BotoCoreError) as e:
        raise HTTPException(status_code=502, detail=f"No se pudo subir a S3: {e}")


def descargar(key: str):
    try:
        return s3.get_object(Bucket=MEDIA_BUCKET, Key=key)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            raise HTTPException(status_code=404, detail="El archivo no esta en S3")
        raise HTTPException(status_code=502, detail=f"Error al leer de S3: {e}")
    except BotoCoreError as e:
        raise HTTPException(status_code=502, detail=f"Error al leer de S3: {e}")


def borrar(key: str) -> None:
    try:
        s3.delete_object(Bucket=MEDIA_BUCKET, Key=key)
    except (ClientError, BotoCoreError) as e:
        raise HTTPException(status_code=502, detail=f"No se pudo borrar de S3: {e}")


def borrar_varios(keys: Iterable[str]) -> None:
    """Borra los objetos antes de que el CASCADE se lleve las filas.

    Si no, las filas de foto_solicitud desaparecen y los objetos quedan
    huerfanos en el bucket, ocupando lugar sin que nada los referencie.
    """
    keys = [k for k in keys if k]
    if not keys:
        return
    try:
        # delete_objects acepta hasta 1000 por llamada.
        for i in range(0, len(keys), 1000):
            s3.delete_objects(
                Bucket=MEDIA_BUCKET,
                Delete={"Objects": [{"Key": k} for k in keys[i : i + 1000]]},
            )
    except (ClientError, BotoCoreError) as e:
        raise HTTPException(status_code=502, detail=f"No se pudieron borrar los objetos: {e}")
