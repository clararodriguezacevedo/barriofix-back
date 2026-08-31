# BarrioFix Backend

API mínima en FastAPI para probar el despliegue en EC2 (ALB → Target Group → ASG) y el acceso a S3
desde subredes privadas vía el Gateway VPC Endpoint. Todavía no hay base de datos: los endpoints de
solicitudes y trabajos devuelven/mutan datos en memoria (`app/data.py`).

## Correr localmente

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/uvicorn app.main:app --reload --port 8080
```

## Endpoints

- `GET /health` → `{"status": "ok"}` (usado por el health check del Target Group)
- `GET /` → mensaje de estado
- `GET /api/requests?categoria=&estado=` → lista de solicitudes
- `GET /api/requests/{id}` → una solicitud
- `POST /api/requests` → crea una solicitud (queda en memoria mientras el proceso viva)
- `PATCH /api/requests/{id}/accept` → asigna un profesional
- `PATCH /api/requests/{id}/status` → cambia el estado
- `POST /api/requests/{id}/rate` → califica un trabajo completado
- `GET /api/jobs?categoria=&urgencia=` → solicitudes pendientes disponibles para tomar
- `GET /api/media?prefix=` → lista objetos del bucket de medios en S3
- `GET /api/media/{key}` → descarga un objeto del bucket de medios en S3

## Variables de entorno

- `MEDIA_BUCKET` (default `barriofix-media-grupo10`)
- `AWS_REGION` (default `us-east-1`)

Las credenciales de AWS no se configuran a mano: `boto3` las toma del rol IAM de la instancia
(`LabInstanceProfile`) vía el servicio de metadata. Desde las subredes privadas, el tráfico a S3 sale
por el Gateway VPC Endpoint (`BarrioFix-s3-endpoint`), no por NAT ni por internet.

## Despliegue en EC2

Ver la guía de infraestructura del proyecto. En resumen: Uvicorn escuchando en `0.0.0.0:8080`,
corriendo como servicio `systemd` (`barriofix-backend.service`, `Restart=always`), desplegado
automáticamente desde el User Data de la Launch Template (`BarrioFix-backend-template`) al clonar
este repo.
