import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/media", tags=["media"])

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
MEDIA_BUCKET = os.environ.get("MEDIA_BUCKET", "barriofix-media-clara")

# Credentials come from the instance's IAM role (LabInstanceProfile) via the
# instance metadata service. Requests to S3 from the private subnets go out
# through the S3 Gateway VPC Endpoint, not the public internet.
s3 = boto3.client("s3", region_name=AWS_REGION)


@router.get("")
def list_media(prefix: str = ""):
    try:
        resp = s3.list_objects_v2(Bucket=MEDIA_BUCKET, Prefix=prefix)
    except (ClientError, BotoCoreError) as e:
        raise HTTPException(status_code=502, detail=f"No se pudo listar el bucket: {e}")
    return [
        {"key": obj["Key"], "size": obj["Size"], "last_modified": obj["LastModified"].isoformat()}
        for obj in resp.get("Contents", [])
    ]


@router.get("/{key:path}")
def get_media(key: str):
    try:
        obj = s3.get_object(Bucket=MEDIA_BUCKET, Key=key)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in ("NoSuchKey", "404"):
            raise HTTPException(status_code=404, detail="Archivo no encontrado")
        raise HTTPException(status_code=502, detail=f"Error al leer de S3: {e}")
    except BotoCoreError as e:
        raise HTTPException(status_code=502, detail=f"Error al leer de S3: {e}")

    content_type = obj.get("ContentType", "application/octet-stream")
    return StreamingResponse(obj["Body"].iter_chunks(), media_type=content_type)
